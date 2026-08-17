"""render.py — MECHANICAL. Join classified reasons with their counts, aggregate,
and emit a Markdown block of Mermaid charts + tables.

Usage:  python skills/report-job-market/scripts/render.py [OUT_DIR]

Consumes from OUT_DIR (default ./.report_tmp):
  timeline.json, reason_dims.json,
  ns_batch<N>.json + ns_result<N>.json, su_batch<N>.json + su_result<N>.json
Writes OUT_DIR/report_body.md and prints headline aggregates.

Each distinct reason is classified once, then that one judgment is spread across
the countries and months the reason actually occurred in (from reason_dims.json).
Country and month slices therefore cost no extra classification and can never
disagree with the overall charts — they are the same numbers, partitioned.

This script makes NO judgments. Categories and skills are supplied by the
classifier subagents; here we only join, tally, and format.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO_ROOT, ".report_tmp")

STRUCTURAL = {"language", "clearance", "work-authorization", "location-onsite"}
FIXABLE = {"missing-skill-stack", "seniority-track", "domain-mismatch"}
CAT_LABEL = {
    "language": "Language requirement",
    "clearance": "Security clearance",
    "work-authorization": "Work authorization",
    "location-onsite": "On-site / relocation",
    "missing-skill-stack": "Missing skill/stack",
    "seniority-track": "Seniority / track mismatch",
    "domain-mismatch": "Different domain/role",
    "other": "Other",
}
LANGS = ["german", "french", "dutch", "swedish", "danish", "portuguese", "spanish", "italian"]
def _load_resume_skills():
    """Load private skill facts locally without committing them.

    The repo root goes on sys.path explicitly: running this file as a script puts
    the *script's* directory on sys.path, not the working directory, so a bare
    `import config_local` fails no matter where it is invoked from. That failure
    is silent and poisons every number — an empty set makes each resume skill
    count as a market gap and makes every strength unmatchable.
    """
    configured = os.getenv("RESUME_SKILLS", "")
    if configured:
        return {skill.strip() for skill in configured.split(",") if skill.strip()}
    sys.path.insert(0, REPO_ROOT)
    try:
        from config_local import RESUME_SKILLS as local_skills
    except (ImportError, AttributeError):
        return set()
    return set(local_skills)


RESUME_SKILLS = _load_resume_skills()
if not RESUME_SKILLS:
    # Rendering anyway would produce a confident, wrong report rather than an
    # obviously broken one, so refuse instead.
    sys.exit(
        "RESUME_SKILLS is empty — set it in config_local.py or the environment. "
        "Without it every resume skill is counted as a market gap and no strength "
        "can ever match."
    )


UNKNOWN_MONTH = "(unknown)"
# A country or month slice built from a handful of rows is noise, not a trend.
MIN_SLICE = 15


def load(name):
    with open(os.path.join(OUT_DIR, name)) as f:
        return json.load(f)


def key_of(reason):
    """Same normalization pull.py keys reason_dims.json by."""
    return re.sub(r"\s+", " ", str(reason).strip()).lower()


def load_classified(prefix, dims):
    """Pair every ns_batch<N>.json with its ns_result<N>.json, in batch order.

    Missing and short result files are fatal rather than skipped: a batch that
    silently vanishes would drop hundreds of rejections out of every chart while
    the page still claimed full coverage.
    """
    batches = sorted(
        (int(re.search(r"(\d+)\.json$", n).group(1)), n)
        for n in os.listdir(OUT_DIR)
        if re.fullmatch(rf"{prefix}_batch\d+\.json", n)
    )
    if not batches:
        sys.exit(f"no {prefix}_batch<N>.json in {OUT_DIR} — run pull.py first")
    out = []
    for i, name in batches:
        result = f"{prefix}_result{i}.json"
        if not os.path.exists(os.path.join(OUT_DIR, result)):
            sys.exit(f"missing {result} — classify {name} before rendering")
        out += zip_batch(load(name), load(result), result, dims)
    return out


def zip_batch(batch, result, label, dims):
    if len(batch) != len(result):
        sys.exit(f"length mismatch in {label}: batch={len(batch)} result={len(result)}")
    for b, r in zip(batch, result):
        r["reason"] = b["reason"]
        r["count"] = b.get("count", r.get("count", 0))
        d = dims.get(key_of(b["reason"]), {})
        r["by_country"] = d.get("by_country", {})
        r["by_month"] = d.get("by_month", {})
    return result


def months_of(timeline):
    """Every real month present, oldest first. `(unknown)` never plots."""
    return sorted({m for months in timeline.values() for m in months if m != UNKNOWN_MONTH})


def pct(part, whole):
    return round(100 * part / whole) if whole else 0


def matrix(title, row_label, rows, columns, cell, total_label="Total"):
    """A counts table with a leading label column and a trailing total.

    `columns` is a list of (header, key) pairs and `cell` is called with the key,
    never the header. Headers are display strings and are not unique — the
    catch-all column is also called "Other", and so is the `other` category —
    so keying cells by header silently makes one column shadow the other.
    """
    out = ([f"**{title}**\n"] if title else []) + [
        "| " + row_label + " | " + " | ".join(h for h, _ in columns) + f" | {total_label} |",
        "|---|" + "---:|" * (len(columns) + 1)]
    for name in rows:
        cells = [cell(name, k) for _, k in columns]
        out.append(f"| {name} | " + " | ".join(str(v) for v in cells) +
                   f" | {sum(cells)} |")
    out.append("")
    return "\n".join(out)


def pie(title, counter, top=8):
    items = counter.most_common()
    head, tail = items[:top], items[top:]
    lines = ["```mermaid", "pie showData", f'    title {title}']
    for k, v in head:
        lines.append(f'    "{k}" : {v}')
    if tail:
        lines.append(f'    "Other" : {sum(v for _, v in tail)}')
    lines.append("```")
    return "\n".join(lines)


def barchart(title, ylabel, counter, top=8):
    items = counter.most_common(top)
    if not items:
        return f"_{title}: no data._"
    labels = ", ".join(f'"{k}"' for k, _ in items)
    values = ", ".join(str(v) for _, v in items)
    ymax = max(v for _, v in items)
    ymax = ((ymax // 10) + 1) * 10
    return "\n".join([
        "```mermaid", "xychart-beta", f'    title "{title}"',
        f"    x-axis [{labels}]", f'    y-axis "{ylabel}" 0 --> {ymax}',
        f"    bar [{values}]", "```",
    ])


def trendchart(title, ylabel, labels, series, ymax=None):
    """Bar + line over the same x-axis — used for the month trends."""
    if not labels:
        return f"_{title}: no data._"
    # An explicit ymax is a real ceiling (100 for a percentage); a derived one
    # gets rounded up so the tallest bar isn't flush with the top of the chart.
    top = ymax or (((max(series) or 1) // 10) + 1) * 10
    return "\n".join([
        "```mermaid", "xychart-beta", f'    title "{title}"',
        "    x-axis [" + ", ".join(f'"{l}"' for l in labels) + "]",
        f'    y-axis "{ylabel}" 0 --> {top}',
        "    bar [" + ", ".join(str(v) for v in series) + "]",
        "    line [" + ", ".join(str(v) for v in series) + "]",
        "```",
    ])


def main():
    timeline = load("timeline.json")
    dims = load("reason_dims.json")
    ns = load_classified("ns", dims["ns"])
    su = load_classified("su", dims["su"])

    cat = Counter()
    tech_gap = Counter()
    lang_split = Counter()
    near_miss = Counter()
    # Same judgments, partitioned by where and when the reason occurred.
    cat_country = defaultdict(Counter)
    cat_month = defaultdict(Counter)
    gap_country = defaultdict(Counter)
    gap_month = defaultdict(Counter)
    ns_country = Counter()
    ns_month = Counter()
    for r in ns:
        c = r.get("category", "other")
        cat[c] += r["count"]
        real_gaps = [s for s in r.get("missing_skills", []) if s not in RESUME_SKILLS]
        for country, n in r["by_country"].items():
            cat_country[country][c] += n
            ns_country[country] += n
            for s in real_gaps:
                gap_country[country][s] += n
        for month, n in r["by_month"].items():
            cat_month[month][c] += n
            ns_month[month] += n
            for s in real_gaps:
                gap_month[month][s] += n
        for s in r.get("missing_skills", []):
            if s not in RESUME_SKILLS:
                tech_gap[s] += r["count"]
        if c == "language":
            low = r["reason"].lower()
            hit = next((l for l in LANGS if l in low), None)
            lang_split[hit.capitalize() if hit else "Unspecified"] += r["count"]
        if c == "missing-skill-stack" and len(real_gaps) == 1:
            near_miss[real_gaps[0]] += r["count"]

    strengths, noted_gaps = Counter(), Counter()
    strength_country = defaultdict(Counter)
    strength_month = defaultdict(Counter)
    for r in su:
        matched = [s for s in r.get("matched_skills", []) if s in RESUME_SKILLS]
        for s in matched:  # a strength must be resume-backed
            strengths[s] += r["count"]
        for country, n in r["by_country"].items():
            for s in matched:
                strength_country[country][s] += n
        for month, n in r["by_month"].items():
            for s in matched:
                strength_month[month][s] += n
        for s in r.get("noted_gaps", []):
            if s not in RESUME_SKILLS:
                noted_gaps[s] += r["count"]

    struct = sum(v for k, v in cat.items() if k in STRUCTURAL)
    fix = sum(v for k, v in cat.items() if k in FIXABLE)
    other = sum(v for k, v in cat.items() if k not in STRUCTURAL and k not in FIXABLE)
    ns_total = sum(cat.values())

    cat_labeled = Counter({CAT_LABEL.get(k, k): v for k, v in cat.items()})
    sf = Counter({"Structural (can't change)": struct, "Fixable (can act on)": fix, "Other": other})

    # Per-country table, built from timeline.json rather than summary.json.
    # summary.json counts raw sheet rows including duplicates; every other table
    # on the page counts deduplicated rows. Mixing the two put the same market at
    # 1042 in one table and 1041 in the next. Coverage still reports the raw
    # counts and the drops — that is where the difference belongs.
    rowsc = []
    for tab, months in timeline.items():
        s = sum(c.get("Suitable", 0) for c in months.values())
        n = sum(c.get("Not Suitable", 0) for c in months.values())
        if s + n == 0:
            continue
        rowsc.append((tab, s, n, pct(s, s + n)))
    rowsc.sort(key=lambda x: x[3], reverse=True)

    # month axis, and the suitable/not split per month across all countries
    months = months_of(timeline)
    month_status = {m: Counter() for m in months}
    country_month = defaultdict(lambda: Counter())
    for country, per_month in timeline.items():
        for m, counts in per_month.items():
            if m == UNKNOWN_MONTH:
                continue
            for status, n in counts.items():
                month_status[m][status] += n
                country_month[country][(m, status)] += n

    # Categories that carry the country/month tables. Anything rarer is folded
    # into the trailing catch-all so a 20-column matrix doesn't hide the signal.
    # `other` is excluded from the named columns even when it ranks top-5: it is
    # the catch-all's own key, and naming it twice makes the two columns collide.
    top_cats = [k for k, _ in cat.most_common() if k != "other"][:5]
    cat_columns = [(CAT_LABEL.get(k, k), k) for k in top_cats] + [("Other", None)]

    def cat_cell(bucket_counter):
        """Cells partition every category, so each row total is its true count."""
        def cell(name, key):
            counts = bucket_counter.get(name, Counter())
            if key is None:
                return sum(v for k, v in counts.items() if k not in top_cats)
            return counts.get(key, 0)
        return cell

    # Skills whose share of rejections moved between the first and last month
    # with enough volume to mean anything.
    # Anchor the comparison on the earliest and latest months that carry enough
    # rejections to compare — a stray one-row month at either end would
    # otherwise reduce every shift to noise, or suppress the section entirely.
    movers, mover_span = [], None
    solid = [m for m in months if ns_month[m] >= MIN_SLICE]
    if len(solid) >= 2:
        first, last = solid[0], solid[-1]
        mover_span = (first, last)
        for skill, _ in tech_gap.most_common(15):
            a = pct(gap_month[first].get(skill, 0), ns_month[first])
            b = pct(gap_month[last].get(skill, 0), ns_month[last])
            movers.append((skill, a, b, b - a))
        movers.sort(key=lambda x: x[3], reverse=True)

    # Every slice is a partition of the same classified rows, so the country and
    # month breakdowns must each re-sum to the overall not-suitable total. If
    # they don't, a category is being dropped or double-counted somewhere in the
    # matrix — fail loudly rather than publish a table that looks authoritative.
    for label, sliced in (("country", ns_country), ("month", ns_month)):
        if sum(sliced.values()) != ns_total:
            sys.exit(f"{label} slices sum to {sum(sliced.values())}, "
                     f"expected {ns_total} — breakdown does not partition the rows")

    B = []
    B.append("## Why jobs are NOT suitable\n")
    B.append(pie("Not-suitable reasons (jobs)", cat_labeled) + "\n")
    B.append(pie("Structural vs fixable", sf) + "\n")
    if lang_split:
        B.append("**Language blockers:** " +
                 ", ".join(f"{k} {v}" for k, v in lang_split.most_common()) + "\n")
    B.append("## Skill gap — what to learn\n")
    B.append("Technologies the market wanted that the resume doesn't show, weighted by jobs:\n")
    B.append(barchart("Top skill gaps", "Jobs", tech_gap) + "\n")
    if near_miss:
        B.append("### Near-miss unlocks (one missing skill away)\n")
        B.append("| Skill | Roles unlocked if learned |\n|---|---:|")
        for k, v in near_miss.most_common(10):
            B.append(f"| {k} | {v} |")
        B.append("")
    B.append("## What makes jobs suitable — your strengths\n")
    B.append(barchart("Strengths credited in suitable jobs", "Jobs", strengths) + "\n")
    if noted_gaps:
        B.append("**Gaps noted even in suitable jobs:** " +
                 ", ".join(f"{k} {v}" for k, v in noted_gaps.most_common(8)) + "\n")
    B.append("## By country\n")
    B.append("### Receptiveness\n")
    B.append("| Country | Suitable | Not suitable | Suitable % |\n|---|---:|---:|---:|")
    for tab, s, n, ratio in rowsc:
        B.append(f"| {tab} | {s} | {n} | {ratio}% |")
    B.append("")
    countries = [c for c, _, _, _ in rowsc if ns_country[c]]
    if countries:
        B.append("### Why each market rejects\n")
        B.append("Rejections by category — the same judgments as the pie above, "
                 "split by market.\n")
        B.append(matrix("", "Country", countries, cat_columns, cat_cell(cat_country),
                        total_label="Rejections"))
        B.append("### What each market wants that you lack\n")
        B.append("| Country | Rejections | Top skill gaps (jobs) |\n|---|---:|---|")
        for c in countries:
            gaps = gap_country[c].most_common(3)
            if ns_country[c] < MIN_SLICE:
                detail = f"_only {ns_country[c]} rejections — too few to read_"
            else:
                detail = ", ".join(f"{k} ({v})" for k, v in gaps) or "—"
            B.append(f"| {c} | {ns_country[c]} | {detail} |")
        B.append("")
        strong = [(c, strength_country[c].most_common(3)) for c in countries
                  if strength_country[c]]
        if strong:
            B.append("**Strengths credited per market:** " + "; ".join(
                f"{c}: " + ", ".join(f"{k} ({v})" for k, v in s) for c, s in strong) + "\n")

    B.append("## By month\n")
    if not months:
        B.append("_No dated rows — monthly breakdown unavailable._\n")
    else:
        B.append("Months are keyed on when a job **entered the pipeline** "
                 "(`scraped_at`), not when it was posted — `date_posted` is blank on "
                 "most rows. Read these as intake and triage trends.\n")
        vols = [month_status[m]["Suitable"] + month_status[m]["Not Suitable"] for m in months]
        rates = [pct(month_status[m]["Suitable"], v) for m, v in zip(months, vols)]
        B.append(trendchart("Jobs triaged per month", "Jobs", months, vols) + "\n")
        B.append(trendchart("Suitable % per month", "% suitable", months, rates, ymax=100) + "\n")
        thin = [f"{m} ({v})" for m, v in zip(months, vols) if v < MIN_SLICE]
        if thin:
            B.append(f"_Plotted but too small to read as a trend: {', '.join(thin)} "
                     f"triaged rows._\n")
        B.append("| Month | Suitable | Not suitable | Total | Suitable % |\n|---|---:|---:|---:|---:|")
        for m, v, rate in zip(months, vols, rates):
            B.append(f"| {m} | {month_status[m]['Suitable']} | "
                     f"{month_status[m]['Not Suitable']} | {v} | {rate}% |")
        B.append("")
        B.append("### Rejection mix by month\n")
        B.append(matrix("", "Month", months, cat_columns, cat_cell(cat_month),
                        total_label="Rejections"))
        B.append("### Skill gaps by month\n")
        B.append("| Month | Rejections | Top skill gaps (jobs) |\n|---|---:|---|")
        for m in months:
            if ns_month[m] < MIN_SLICE:
                detail = f"_only {ns_month[m]} rejections — too few to read_"
            else:
                detail = ", ".join(f"{k} ({v})" for k, v in gap_month[m].most_common(3)) or "—"
            B.append(f"| {m} | {ns_month[m]} | {detail} |")
        B.append("")
        if movers:
            B.append(f"### Demand shift, {mover_span[0]} → {mover_span[1]}\n")
            B.append("Share of that month's rejections naming the skill, so months of "
                     "different size stay comparable.\n")
            B.append(f"| Skill | {mover_span[0]} | {mover_span[1]} | Change |\n|---|---:|---:|---:|")
            risers = movers[:5]
            fallers = [m for m in reversed(movers) if m not in risers][:5]
            for skill, a, b, delta in risers + fallers:
                B.append(f"| {skill} | {a}% | {b}% | {delta:+d} pts |")
            B.append("")
        if countries:
            B.append("### Suitable % by country and month\n")
            B.append("Blank where that market had no triaged rows that month.\n")
            B.append("| Country | " + " | ".join(months) + " |")
            B.append("|---|" + "---:|" * len(months))
            for c in countries:
                cells = []
                for m in months:
                    s = country_month[c][(m, "Suitable")]
                    n = country_month[c][(m, "Not Suitable")]
                    cells.append(f"{pct(s, s + n)}% ({s + n})" if s + n else "—")
                B.append(f"| {c} | " + " | ".join(cells) + " |")
            B.append("")

    with open(os.path.join(OUT_DIR, "report_body.md"), "w") as f:
        f.write("\n".join(B))

    print(f"not-suitable reasoned rows: {ns_total}")
    print(f"structural={struct} fixable={fix} other={other}")
    print("top categories:", cat_labeled.most_common(5))
    print("top skill gaps:", tech_gap.most_common(8))
    print("top strengths:", strengths.most_common(6))
    print("languages:", lang_split.most_common())
    print("countries with rejections:", ns_country.most_common())
    print("months:", ", ".join(
        f"{m}: {month_status[m]['Suitable'] + month_status[m]['Not Suitable']} rows / "
        f"{pct(month_status[m]['Suitable'], month_status[m]['Suitable'] + month_status[m]['Not Suitable'])}% suitable"
        for m in months) or "none")
    if movers:
        print("biggest demand shift:", [(s, f"{d:+d}pts") for s, _, _, d in movers[:3]])
    print(f"wrote {os.path.join(OUT_DIR, 'report_body.md')}")


if __name__ == "__main__":
    main()
