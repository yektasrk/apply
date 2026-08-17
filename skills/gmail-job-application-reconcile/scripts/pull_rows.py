"""pull_rows.py — MECHANICAL, read-only. Pull the tracker columns needed to match
job-application email to rows.

Usage:  python skills/gmail-job-application-reconcile/scripts/pull_rows.py [OUT_DIR]

Writes to OUT_DIR (default ./.reconcile_tmp):
  - rows.json  : every non-empty row, matching columns only, with tab + row number
  - by_url.json: normalized job_url -> [{tab, row}], the exact-match index
  - gaps.json  : rows whose job_status is Applied but application_result is blank

This script makes NO classification or matching decisions. It only reads.

Only the matching columns are pulled. `description` alone runs to thousands of
characters a row across ~2,900 rows, and nothing in this workflow matches on it,
so fetching whole rows would cost a large multiple of the data for no gain.

`by_url.json` exists because a job URL is the one signal that settles a match on
its own — company and title both collapse across rows ("DevOps Engineer" appears
on dozens). LinkedIn application mail carries the posting id in its body, so
resolving it against this index turns a guess into an exact hit.

`gaps.json` is the run's real worklist: an Applied row with no result is an
application whose outcome was never recorded.

Sheet access comes from job_finder.sheets, which is also what the scraper uses.
Spreadsheet id and service-account path resolve through job_finder.config
(env, then config_local.py), so this script needs no configuration of its own.
"""
import json
import os
import re
import sys
from collections import defaultdict

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)

from job_finder import config, sheets  # noqa: E402

# The columns matching actually reads. Anything absent from a tab is emitted as "".
KEEP = (
    "job_status",
    "application_result",
    "title",
    "company",
    "location",
    "job_url",
    "applied_at",
    "application_notes",
)

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO_ROOT, ".reconcile_tmp")

RESULT_COLUMN = "application_result"
APPLIED_STATUS = "applied"


def norm_url(url):
    """Reduce a job URL to the part that identifies the posting.

    LinkedIn appends per-email tracking query strings, so the raw URL in a
    message never equals the raw URL in the sheet. Comparing the bare path is
    what makes the index hit at all.
    """
    url = str(url).strip()
    if not url:
        return ""
    url = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return url.lower()


def linkedin_id(url):
    """Return the LinkedIn posting id, when the URL is a LinkedIn job link.

    Emails and the sheet sometimes carry different LinkedIn host spellings for
    the same posting, so the numeric id is the more durable key of the two.
    """
    m = re.search(r"/jobs/view/(\d+)", str(url))
    return m.group(1) if m else ""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    if not config.GOOGLE_SHEET_ID:
        sys.exit(
            "GOOGLE_SHEET_ID is not set. Expected it in config_local.py at the repo "
            "root, or in the environment."
        )

    spreadsheet = sheets.get_spreadsheet()

    rows, by_url, gaps = [], defaultdict(list), []
    tabs = {}

    for worksheet in spreadsheet.worksheets():
        values = worksheet.get_all_values()
        if not values:
            tabs[worksheet.title] = {"sheet_id": worksheet.id, "rows": 0}
            continue

        header = [str(h).strip() for h in values[0]]
        index = {name: i for i, name in enumerate(header)}
        if RESULT_COLUMN not in index:
            # A tab without the result column cannot be reconciled; say so rather
            # than silently emitting rows the write step could never target.
            print(f"  ! {worksheet.title}: no {RESULT_COLUMN} column, skipped", file=sys.stderr)
            tabs[worksheet.title] = {"sheet_id": worksheet.id, "rows": 0, "skipped": True}
            continue

        count = 0
        for row_number, raw in enumerate(values[1:], start=2):
            if not any(raw):
                continue
            record = {"tab": worksheet.title, "row": row_number}
            for column in KEEP:
                i = index.get(column)
                record[column] = raw[i].strip() if i is not None and i < len(raw) else ""
            rows.append(record)
            count += 1

            key = norm_url(record["job_url"])
            if key:
                by_url[key].append({"tab": worksheet.title, "row": row_number})
            job_id = linkedin_id(record["job_url"])
            if job_id:
                by_url[f"linkedin:{job_id}"].append(
                    {"tab": worksheet.title, "row": row_number}
                )

            if (
                record["job_status"].lower() == APPLIED_STATUS
                and not record[RESULT_COLUMN]
            ):
                gaps.append(record)

        tabs[worksheet.title] = {"sheet_id": worksheet.id, "rows": count}

    write(os.path.join(OUT_DIR, "rows.json"), {"tabs": tabs, "rows": rows})
    write(os.path.join(OUT_DIR, "by_url.json"), dict(by_url))
    write(os.path.join(OUT_DIR, "gaps.json"), gaps)

    ambiguous = {k: v for k, v in by_url.items() if len(v) > 1}
    print(f"spreadsheet : {spreadsheet.title}")
    print(f"tabs        : {len(tabs)}")
    print(f"rows        : {len(rows)}")
    print(f"url keys    : {len(by_url)} ({len(ambiguous)} pointing at >1 row)")
    print(f"gaps        : {len(gaps)} Applied rows with a blank {RESULT_COLUMN}")
    print(f"out         : {OUT_DIR}")


def write(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
