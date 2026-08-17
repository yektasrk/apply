"""write_results.py — apply application_result changes to the tracker, safely.

Usage:
    python skills/gmail-job-application-reconcile/scripts/write_results.py CHANGES.json
    python skills/gmail-job-application-reconcile/scripts/write_results.py CHANGES.json --commit

CHANGES.json is a list of objects. `company` is required and is verified against
the sheet before anything is written:

    [
      {"tab": "Germany", "row": 136, "value": "Resume Reject",
       "company": "PAIR Finance", "title": "DevOps Engineer (f/m/d)",
       "why": "08-05 rejection, exact role"}
    ]

Without --commit this is a dry run: it reports what would change and writes nothing.

Why the company check is mandatory. A row number is a coordinate into a sheet the
user also edits by hand, and the archiver deletes rows outright — so the number
that was correct when the mail was matched can point at a different job by the
time the write runs. Re-reading company (and title, when supplied) immediately
before writing is what makes a stale coordinate fail loudly instead of silently
stamping an outcome onto someone else's job.

Everything else here enforces rules the skill states in prose:
  - only `application_result` is touched, resolved by header name, never by a
    hardcoded column letter;
  - only the three allowed values are accepted;
  - cells already holding the target value are skipped, so a re-run is a no-op;
  - one batchUpdate of one-cell updateCells requests with fields=userEnteredValue,
    which cannot disturb neighbouring cells, notes, or formatting;
  - every changed cell is read back afterwards and the final value printed.

Sheet access comes from job_finder.sheets, the same client the scraper uses.
"""
import json
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)

from job_finder import config, sheets  # noqa: E402

RESULT_COLUMN = "application_result"
ALLOWED = ("Resume Send", "Resume Reject", "Online Meeting")


def fail(message):
    sys.exit(f"ERROR: {message}")


def norm(text):
    return " ".join(str(text or "").split()).casefold()


def load_changes(path):
    with open(path, encoding="utf-8") as handle:
        changes = json.load(handle)
    if not isinstance(changes, list) or not changes:
        fail("input must be a non-empty JSON list")
    for i, change in enumerate(changes):
        for field in ("tab", "row", "value", "company"):
            if not change.get(field):
                fail(f"item {i}: missing required field {field!r}")
        if change["value"] not in ALLOWED:
            fail(f"item {i}: value {change['value']!r} is not one of {ALLOWED}")
        if not isinstance(change["row"], int) or change["row"] < 2:
            fail(f"item {i}: row must be an integer >= 2 (row 1 is the header)")
    seen = {(c["tab"], c["row"]) for c in changes}
    if len(seen) != len(changes):
        fail("two changes target the same cell")
    return changes


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    commit = "--commit" in sys.argv[1:]
    if len(args) != 1:
        fail("expected exactly one CHANGES.json path")
    changes = load_changes(args[0])

    if not config.GOOGLE_SHEET_ID:
        fail("GOOGLE_SHEET_ID is not set (expected in config_local.py or the environment)")

    spreadsheet = sheets.get_spreadsheet()
    worksheets = {ws.title: ws for ws in spreadsheet.worksheets()}

    missing = {c["tab"] for c in changes} - set(worksheets)
    if missing:
        fail(f"no such tab(s): {sorted(missing)}")

    # One read per tab for the header, one per target row. Done before any write
    # so a mismatch anywhere aborts the whole batch rather than leaving it half
    # applied.
    headers = {}
    for tab in {c["tab"] for c in changes}:
        header = [str(h).strip() for h in worksheets[tab].row_values(1)]
        if RESULT_COLUMN not in header:
            fail(f"tab {tab!r} has no {RESULT_COLUMN} column")
        headers[tab] = header

    planned, skipped = [], []
    for change in changes:
        tab, row = change["tab"], change["row"]
        header = headers[tab]
        values = worksheets[tab].row_values(row)
        values += [""] * (len(header) - len(values))
        record = dict(zip(header, values))

        actual_company = record.get("company", "")
        if norm(actual_company) != norm(change["company"]):
            fail(
                f"{tab} row {row}: company mismatch — sheet has {actual_company!r}, "
                f"change claims {change['company']!r}. The row number is stale; "
                f"re-run pull_rows.py and re-match."
            )
        if change.get("title") and norm(record.get("title", "")) != norm(change["title"]):
            fail(
                f"{tab} row {row}: title mismatch — sheet has "
                f"{record.get('title', '')!r}, change claims {change['title']!r}."
            )

        current = record.get(RESULT_COLUMN, "")
        entry = {
            **change,
            "column_index": header.index(RESULT_COLUMN),
            "sheet_id": worksheets[tab].id,
            "current": current,
        }
        (skipped if current == change["value"] else planned).append(entry)

    for entry in skipped:
        print(f"  = {entry['tab']} r{entry['row']:<5} already {entry['value']!r} — skipped")
    for entry in planned:
        arrow = f"{entry['current'] or '(blank)'!r} -> {entry['value']!r}"
        print(f"  ~ {entry['tab']} r{entry['row']:<5} {arrow}  [{entry['company']}]")
        if entry.get("why"):
            print(f"      why: {entry['why']}")

    if not planned:
        print("\nnothing to change.")
        return
    if not commit:
        print(f"\ndry run — {len(planned)} cell(s) would change. Re-run with --commit.")
        return

    requests = [
        {
            "updateCells": {
                "range": {
                    "sheetId": entry["sheet_id"],
                    "startRowIndex": entry["row"] - 1,
                    "endRowIndex": entry["row"],
                    "startColumnIndex": entry["column_index"],
                    "endColumnIndex": entry["column_index"] + 1,
                },
                "rows": [
                    {"values": [{"userEnteredValue": {"stringValue": entry["value"]}}]}
                ],
                "fields": "userEnteredValue",
            }
        }
        for entry in planned
    ]
    reply = spreadsheet.batch_update({"requests": requests})
    print(f"\nbatchUpdate applied: {len(reply.get('replies', []))} request(s)")

    print("verify (re-read):")
    ok = True
    for entry in planned:
        cell = worksheets[entry["tab"]].cell(entry["row"], entry["column_index"] + 1).value
        good = cell == entry["value"]
        ok = ok and good
        print(f"  {'ok ' if good else 'BAD'} {entry['tab']} r{entry['row']:<5} = {cell!r}")
    if not ok:
        fail("at least one cell did not hold its expected value after the write")


if __name__ == "__main__":
    main()
