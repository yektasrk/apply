"""pull.py — MECHANICAL, read-only. Pull triaged rows from the job sheets and emit
deduplicated reason batches for classification.

Usage:  python skills/report-job-market/scripts/pull.py [OUT_DIR]

Reads every tab of BOTH spreadsheets — the live sheet and the archive sheet that
not-suitable rows are moved to — keeps rows whose job_status is Suitable / Yes /
Not Suitable, and writes to OUT_DIR (default ./.report_tmp):
  - summary.json     : per-country status counts, live and archive merged
  - coverage.json    : the same counts split by source, plus dedup/config notes
  - ns_batch1.json   : distinct not-suitable reasons (with counts), first half
  - ns_batch2.json   : distinct not-suitable reasons (with counts), second half
  - su_batch.json    : distinct suitable reasons (with counts)
  - triaged.json     : full triaged rows (for optional deeper analysis)

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
        "is_remote", "location", "date_posted", "description", "job_url")


def norm(t):
    return re.sub(r"\s+", " ", str(t).strip())


def distinct(rows):
    reps, cnt = {}, Counter()
    for r in rows:
        key = norm(r["suitability_reason"]).lower()
        cnt[key] += 1
        reps.setdefault(key, norm(r["suitability_reason"]))
    return [{"reason": reps[k], "count": c} for k, c in cnt.most_common()]


def open_sheet(sheet_id):
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SA_FILE, scopes=scopes)
    return gspread.authorize(creds).open_by_key(sheet_id)


def read_source(sheet_id, source, rows, seen_urls, summary, coverage, duplicates):
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

            rows.append({
                "country": ws.title,
                "source": source,
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

    read_source(SHEET_ID, "live", rows, seen_urls, summary, coverage, duplicates)
    read_source(ARCHIVE_SHEET_ID, "archive", rows, seen_urls, summary, coverage, duplicates)

    ns = [r for r in rows if r["job_status"].lower() == "not suitable" and r["suitability_reason"]]
    su = [r for r in rows if r["job_status"].lower() in ("suitable", "yes") and r["suitability_reason"]]
    nsd, sud = distinct(ns), distinct(su)
    half = len(nsd) // 2

    def dump(name, obj):
        with open(os.path.join(OUT_DIR, name), "w") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)

    dump("summary.json", {tab: dict(counts) for tab, counts in summary.items()})
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
    })
    dump("ns_batch1.json", nsd[:half])
    dump("ns_batch2.json", nsd[half:])
    dump("su_batch.json", sud)
    dump("triaged.json", rows)

    live_rows = sum(1 for r in rows if r["source"] == "live")
    archive_rows = len(rows) - live_rows
    print(f"OUT_DIR={OUT_DIR}")
    print(f"triaged rows: {len(rows)}  (live={live_rows}, archive={archive_rows})")
    print(f"  reasoned: not-suitable={len(ns)}, suitable={len(su)}")
    print(f"distinct: ns={len(nsd)} (batches {half}/{len(nsd)-half}), su={len(sud)}")
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
