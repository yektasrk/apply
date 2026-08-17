"""pull.py — MECHANICAL, read-only. Pull triaged rows from the job sheets and emit
deduplicated reason batches for classification.

Usage:  python skills/report-job-market/scripts/pull.py [OUT_DIR]

Reads every tab of BOTH spreadsheets — the live sheet and the archive sheet that
not-suitable rows are moved to — keeps rows whose job_status is Suitable / Yes /
Not Suitable, and writes to OUT_DIR (default ./.report_tmp):
  - summary.json     : per-country status counts, live and archive merged
  - timeline.json    : country -> month -> {Suitable, Not Suitable} counts
  - coverage.json    : the same counts split by source, plus dedup/month/config notes
  - reason_dims.json : per distinct reason, its country and month breakdown
  - ns_batch<N>.json : distinct not-suitable reasons (with counts), chunked
  - su_batch<N>.json : distinct suitable reasons (with counts), chunked
  - triaged.json     : full triaged rows (for optional deeper analysis)

The country and month breakdown of each distinct reason lives in
`reason_dims.json`, deliberately NOT in the `*_batch.json` files: a classifier
subagent only needs the reason text, and padding its input with per-country
tallies would cost tokens and invite it to reason about volume instead of
meaning. render.py rejoins the two on the normalized reason string.

Reading both sheets is not optional. Not-suitable rows are deleted from the live
sheet once archived, so a live-only report would silently lose every rejection
reason ever archived and overstate how suitable the market looks.

summary.json merges the two sources per country because a country's
suitable-vs-not ratio is a fact about the country, not about which spreadsheet a
row currently sits in. render.py consumes that shape. coverage.json keeps the
split so the report's Coverage section can state what came from where.

This script makes NO suitability or category decisions. It only reads and tallies.
Sheet ids / service-account come from config_local.py, then env, then defaults.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

import gspread
from google.oauth2.service_account import Credentials

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _cfg(name, default):
    # prefer repo-root config_local.py, then env, then default
    sys.path.insert(0, REPO_ROOT)
    try:
        import config_local  # type: ignore
        val = getattr(config_local, name, None)
        if val:
            return val
    except Exception:
        pass
    return os.getenv(name, default)


SHEET_ID = _cfg("GOOGLE_SHEET_ID", "")
ARCHIVE_SHEET_ID = _cfg("GOOGLE_ARCHIVE_SHEET_ID", "")
SA_FILE = _cfg("GOOGLE_SERVICE_ACCOUNT_FILE", os.path.join(REPO_ROOT, "service_account.json"))
if not os.path.isabs(SA_FILE):
    SA_FILE = os.path.join(REPO_ROOT, SA_FILE)

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO_ROOT, ".report_tmp")
os.makedirs(OUT_DIR, exist_ok=True)

TRIAGED = {"suitable", "not suitable", "yes"}
KEEP = ("title", "company", "job_status", "suitability_reason", "job_level",
        "is_remote", "location", "scraped_at", "date_posted", "description", "job_url")

MONTH_RE = re.compile(r"^(\d{4})-(\d{2})")
UNKNOWN_MONTH = "(unknown)"

# Distinct reasons per classifier subagent. Batches are sized, not halved: the
# sheet now backs a few thousand distinct reason strings, and a subagent asked to
# emit one object per input across a batch that large will truncate — which
# render.py then rejects as a length mismatch. ~200 keeps each subagent's output
# comfortably short and makes a retry cheap when one does drift.
BATCH_SIZE = int(_cfg("REPORT_BATCH_SIZE", 200))


def norm(t):
    return re.sub(r"\s+", " ", str(t).strip())


def month_of(row):
    """Bucket a row into a YYYY-MM month, and say which column it came from.

    `scraped_at` is the primary axis, not `date_posted`: the scraper stamps it on
    every row it writes, while `date_posted` comes from the job board and is
    blank on the large majority of rows. A month therefore means "when this job
    entered the pipeline", not "when the employer posted it".

    date_posted is only a fallback for the rare row with no scraped_at. Mixing
    the two bases per-row would be worse than either alone — a job posted in May
    but scraped in July would sit a bucket away from its own cohort — so the
    fallback stays rare by construction and coverage.json reports how often it
    fired.
    """
    for basis in ("scraped_at", "date_posted"):
        m = MONTH_RE.match(norm(row.get(basis, "")))
        if m:
            return f"{m.group(1)}-{m.group(2)}", basis
    return UNKNOWN_MONTH, "none"


def status_bucket(status):
    """Collapse the triage vocabulary to the two buckets the charts use."""
    return "Suitable" if status.lower() in ("suitable", "yes") else "Not Suitable"


def distinct(rows):
    """Deduplicate reason strings, keeping each one's country and month spread.

    Returns (batch, dims): `batch` is the lean list handed to the classifier
    subagents, `dims` maps the same normalized key to the breakdown render.py
    needs to slice categories and skills by country and by month.
    """
    reps, cnt = {}, Counter()
    by_country, by_month = defaultdict(Counter), defaultdict(Counter)
    for r in rows:
        key = norm(r["suitability_reason"]).lower()
        cnt[key] += 1
        reps.setdefault(key, norm(r["suitability_reason"]))
        by_country[key][r["country"]] += 1
        by_month[key][r["month"]] += 1
    batch = [{"reason": reps[k], "count": c} for k, c in cnt.most_common()]
    dims = {
        k: {
            "reason": reps[k],
            "count": c,
            "by_country": dict(by_country[k]),
            "by_month": dict(by_month[k]),
        }
        for k, c in cnt.most_common()
    }
    return batch, dims


def open_sheet(sheet_id):
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SA_FILE, scopes=scopes)
    return gspread.authorize(creds).open_by_key(sheet_id)


def read_source(sheet_id, source, rows, seen_urls, summary, coverage, duplicates,
                timeline, month_basis):
    """Tally one spreadsheet into the shared accumulators.

    Two different duplicate kinds are counted separately because they mean
    different things: `within_source` is the same job on two rows of one
    spreadsheet (a data issue worth knowing about), while `across_sources` is a
    row the archiver has appended but not yet deleted from the live sheet (a
    normal, transient state mid-run).
    """
    source_urls = set()
    for ws in open_sheet(sheet_id).worksheets():
        header = [str(h).strip() for h in ws.row_values(1)]
        if not any(header):
            # An untouched default tab (e.g. the archive's Sheet1) has no header
            # and no rows; get_all_records() would choke on it.
            continue

        counts = Counter()
        for r in ws.get_all_records():
            status = norm(r.get("job_status", ""))
            counts[status or "(blank)"] += 1
            if status.lower() not in TRIAGED:
                continue

            url = norm(r.get("job_url", ""))
            if url:
                if url in source_urls:
                    duplicates["within_source"] += 1
                    continue
                if url in seen_urls:
                    duplicates["across_sources"] += 1
                    continue
                source_urls.add(url)
                seen_urls.add(url)

            month, basis = month_of(r)
            month_basis[basis] += 1
            timeline[ws.title][month][status_bucket(status)] += 1
            rows.append({
                "country": ws.title,
                "source": source,
                "month": month,
                "month_basis": basis,
                **{k: norm(r.get(k, "")) for k in KEEP},
            })

        coverage[source][ws.title] = dict(counts)
        for status, n in counts.items():
            summary[ws.title][status] += n


def main():
    if not SHEET_ID:
        sys.exit("GOOGLE_SHEET_ID not found in config_local.py or env.")
    if not ARCHIVE_SHEET_ID:
        sys.exit(
            "GOOGLE_ARCHIVE_SHEET_ID not found in config_local.py or env. "
            "Not-suitable rows are deleted from the live sheet once archived, so "
            "a live-only report would silently drop every archived rejection "
            "reason. Set it before reporting."
        )

    rows, seen_urls = [], set()
    summary = defaultdict(Counter)
    coverage = {"live": {}, "archive": {}}
    duplicates = Counter()
    timeline = defaultdict(lambda: defaultdict(Counter))
    month_basis = Counter()

    read_source(SHEET_ID, "live", rows, seen_urls, summary, coverage, duplicates,
                timeline, month_basis)
    read_source(ARCHIVE_SHEET_ID, "archive", rows, seen_urls, summary, coverage,
                duplicates, timeline, month_basis)

    ns = [r for r in rows if r["job_status"].lower() == "not suitable" and r["suitability_reason"]]
    su = [r for r in rows if r["job_status"].lower() in ("suitable", "yes") and r["suitability_reason"]]
    nsd, ns_dims = distinct(ns)
    sud, su_dims = distinct(su)

    def dump(name, obj):
        with open(os.path.join(OUT_DIR, name), "w") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)

    dump("summary.json", {tab: dict(counts) for tab, counts in summary.items()})
    dump("timeline.json", {
        tab: {month: dict(counts) for month, counts in sorted(months.items())}
        for tab, months in timeline.items()
    })
    dump("coverage.json", {
        "by_source": coverage,
        # Chart totals equal summary.json's triaged totals MINUS these. Stated
        # explicitly so the report's Coverage section can reconcile the two
        # instead of a reader assuming a silent undercount.
        "duplicates_dropped": dict(duplicates),
        "triaged_rows": {
            "live": sum(1 for r in rows if r["source"] == "live"),
            "archive": sum(1 for r in rows if r["source"] == "archive"),
        },
        # Which column each row's month came from. The report must say this out
        # loud: a monthly trend built on scraped_at describes pipeline intake,
        # and reads as posting demand only if nobody states the difference.
        "month_basis": dict(month_basis),
        "months_seen": sorted(
            {m for months in timeline.values() for m in months if m != UNKNOWN_MONTH}
        ),
    })
    dump("reason_dims.json", {"ns": ns_dims, "su": su_dims})

    def dump_batches(prefix, items):
        chunks = [items[i:i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)] or [[]]
        for i, chunk in enumerate(chunks, 1):
            dump(f"{prefix}_batch{i}.json", chunk)
        return len(chunks)

    ns_batches = dump_batches("ns", nsd)
    su_batches = dump_batches("su", sud)
    dump("triaged.json", rows)

    live_rows = sum(1 for r in rows if r["source"] == "live")
    archive_rows = len(rows) - live_rows
    print(f"OUT_DIR={OUT_DIR}")
    print(f"triaged rows: {len(rows)}  (live={live_rows}, archive={archive_rows})")
    print(f"  reasoned: not-suitable={len(ns)}, suitable={len(su)}")
    print(f"distinct: ns={len(nsd)} in {ns_batches} batch(es), "
          f"su={len(sud)} in {su_batches} batch(es), size={BATCH_SIZE}")
    months = sorted({m for months in timeline.values() for m in months if m != UNKNOWN_MONTH})
    print(f"months: {', '.join(months) or 'none'}  "
          f"(basis: {dict(month_basis)})")
    if month_basis["none"]:
        print(f"  {month_basis['none']} row(s) have no usable date — bucketed as {UNKNOWN_MONTH}")
    if duplicates["within_source"]:
        print(f"dropped {duplicates['within_source']} row(s) duplicated inside one "
              f"spreadsheet — the same job on two rows")
    if duplicates["across_sources"]:
        print(f"dropped {duplicates['across_sources']} row(s) in both sheets "
              f"(archiver appended but has not deleted the live row yet)")
    for source in ("live", "archive"):
        tabs = coverage[source]
        if tabs:
            print(f"  {source}:")
            for tab, counts in tabs.items():
                print(f"    {tab}: {counts}")


if __name__ == "__main__":
    main()
