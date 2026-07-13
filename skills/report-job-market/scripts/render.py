"""render.py — MECHANICAL. Join classified reasons with their counts, aggregate,
and emit a Markdown block of Mermaid charts + tables.

Usage:  python skills/report-job-market/scripts/render.py [OUT_DIR]

Consumes from OUT_DIR (default ./.report_tmp):
  summary.json, ns_batch1.json, ns_batch2.json, su_batch.json,
  ns_result1.json, ns_result2.json, su_result.json
Writes OUT_DIR/report_body.md and prints headline aggregates.

This script makes NO judgments. Categories and skills are supplied by the
classifier subagents; here we only join, tally, and format.
"""
import json
import os
import re
import sys
from collections import Counter

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
# Candidate-specific skills are supplied at runtime and are intentionally not
# committed. Set RESUME_SKILLS as a comma-separated environment variable when
# generating a private report.
RESUME_SKILLS = {
    skill.strip()
    for skill in os.getenv("RESUME_SKILLS", "").split(",")
    if skill.strip()
}


def load(name):
    with open(os.path.join(OUT_DIR, name)) as f:
        return json.load(f)


def zip_batch(batch, result, label):
    if len(batch) != len(result):
        sys.exit(f"length mismatch in {label}: batch={len(batch)} result={len(result)}")
    for b, r in zip(batch, result):
        r["reason"] = b["reason"]
        r["count"] = b.get("count", r.get("count", 0))
    return result


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


def main():
    summary = load("summary.json")
    ns = zip_batch(load("ns_batch1.json"), load("ns_result1.json"), "ns1") + \
        zip_batch(load("ns_batch2.json"), load("ns_result2.json"), "ns2")
    su = zip_batch(load("su_batch.json"), load("su_result.json"), "su")

    cat = Counter()
    tech_gap = Counter()
    lang_split = Counter()
    near_miss = Counter()
    for r in ns:
        c = r.get("category", "other")
        cat[c] += r["count"]
        for s in r.get("missing_skills", []):
            if s not in RESUME_SKILLS:
                tech_gap[s] += r["count"]
        if c == "language":
            low = r["reason"].lower()
            hit = next((l for l in LANGS if l in low), None)
            lang_split[hit.capitalize() if hit else "Unspecified"] += r["count"]
        real_missing = [s for s in r.get("missing_skills", []) if s not in RESUME_SKILLS]
        if c == "missing-skill-stack" and len(real_missing) == 1:
            near_miss[real_missing[0]] += r["count"]

    strengths, noted_gaps = Counter(), Counter()
    for r in su:
        for s in r.get("matched_skills", []):
            if s in RESUME_SKILLS:  # a strength must be resume-backed
                strengths[s] += r["count"]
        for s in r.get("noted_gaps", []):
            if s not in RESUME_SKILLS:
                noted_gaps[s] += r["count"]

    struct = sum(v for k, v in cat.items() if k in STRUCTURAL)
    fix = sum(v for k, v in cat.items() if k in FIXABLE)
    other = sum(v for k, v in cat.items() if k not in STRUCTURAL and k not in FIXABLE)
    ns_total = sum(cat.values())

    cat_labeled = Counter({CAT_LABEL.get(k, k): v for k, v in cat.items()})
    sf = Counter({"Structural (can't change)": struct, "Fixable (can act on)": fix, "Other": other})

    # per-country table
    rowsc = []
    for tab, counts in summary.items():
        s = counts.get("Suitable", 0) + counts.get("Yes", 0)
        n = counts.get("Not Suitable", 0)
        if s + n == 0:
            continue
        ratio = round(100 * s / (s + n))
        rowsc.append((tab, s, n, ratio))
    rowsc.sort(key=lambda x: x[3], reverse=True)

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
    B.append("## Per-country receptiveness\n")
    B.append("| Country | Suitable | Not suitable | Suitable % |\n|---|---:|---:|---:|")
    for tab, s, n, ratio in rowsc:
        B.append(f"| {tab} | {s} | {n} | {ratio}% |")
    B.append("")

    with open(os.path.join(OUT_DIR, "report_body.md"), "w") as f:
        f.write("\n".join(B))

    print(f"not-suitable reasoned rows: {ns_total}")
    print(f"structural={struct} fixable={fix} other={other}")
    print("top categories:", cat_labeled.most_common(5))
    print("top skill gaps:", tech_gap.most_common(8))
    print("top strengths:", strengths.most_common(6))
    print("languages:", lang_split.most_common())
    print(f"wrote {os.path.join(OUT_DIR, 'report_body.md')}")


if __name__ == "__main__":
    main()
