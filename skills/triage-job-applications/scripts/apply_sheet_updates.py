#!/usr/bin/env python3
"""
apply_sheet_updates.py — reusable, MECHANICAL Google Sheet writer.

This script only *applies* values that an agent (or user) has already authored.
It never decides suitability, never drafts reasons or prose, and never reads a
resume or job description. It reads sheet cells, writes the values it is given,
enforces the sheet's safety guards, and verifies the write. That keeps it inside
the triage/submit skills' generation boundary: substantive outputs are authored
by the agent; the script is plumbing.

Usage
-----
    python skills/triage-job-applications/scripts/apply_sheet_updates.py \
        --input updates.json          # apply the updates
    python .../apply_sheet_updates.py --input updates.json --check   # dry run
    python .../apply_sheet_updates.py --input updates.json --remap   # fix shifted rows

Input JSON schema
-----------------
    {
      "spreadsheet_id": "1lfY...",          # optional; see resolution order below
      "tab": "Germany",                      # required — worksheet/tab name
      "terminal_statuses": ["Closed", ...],  # optional; extends the default set
      "allow_nonblank_application_result": false,  # optional; see below
      "remap_by_job_url": false,             # optional; same as --remap
      "updates": [
        {"row": 1527, "job_status": "Suitable", "suitability_reason": "...",
         "expect": {"job_url": "https://www.linkedin.com/jobs/view/4448866107"}},
        {"row": 1529, "job_status": "Not Suitable", "suitability_reason": "..."},
        {"row": 1561, "cover_letter_path": "/abs/path/Company.md"}
      ]
    }

Every key in an update object other than "row" and "expect" is a *column header
name* from the tab's header row (row 1). Columns are matched by name, so this
works across tabs with different schemas. A field naming a column that does not
exist in the header is a hard error (create the column first, e.g.
`suitability_reason`).

Row identity (`expect`)
-----------------------
Row numbers are positional, not stable: if rows are deleted from the tab between
the read that produced your decisions and this write — an archive/cleanup run, or
the user editing the sheet — every row number below the deletion point now points
at a different job. Read-back verification does NOT catch this, because the cell
does hold the value you sent; it is simply the wrong row.

Guard against that by attaching an `expect` block naming the row's stable
identifier, normally `job_url`, captured in the same read that produced the
decision. Before writing anything, every `expect` is checked against the live
sheet; any mismatch aborts the entire run with a report of what was found instead
and, where the identifier can still be located, the row it moved to. Identity is
re-verified after the write as well, which closes the race between the pre-flight
read and the write itself.

`expect` accepts any column, but use stable identifiers (`job_url`) — comparison
is exact after whitespace stripping, so volatile columns like `description` will
produce spurious failures.

Pass `--remap` (or `"remap_by_job_url": true`) to have mismatched rows relocated
automatically by their `expect.job_url` instead of aborting. The remap is
reported in the summary. It requires `job_url` to be unique within the tab.

`expect.job_url` is MANDATORY on every update — triage decisions and submission
outcomes alike. It is checked before the sheet is even read, so an unidentified
batch costs one cheap failure and writes nothing. There is no opt-in flag to
forget: the only way past it is `"allow_missing_expect": true`, which is for a
single hand-checked row you are looking at, not for making a batch go through.

Safety guards (mirror the skills' Sheet Contract / Update Safety)
-----------------------------------------------------------------
- Rows with a nonblank `application_result` are skipped entirely. The submit
  skill records a result on a fresh (blank) row, so its normal writes pass; set
  `"allow_nonblank_application_result": true` only for a user-approved retry of a
  row that already carries a result.
- Rows whose current `job_status` is a terminal value (default:
  Closed / Resume Send / Resume Reject) are skipped entirely.
- A nonblank `cover_letter_path` is never overwritten (that field is skipped;
  the rest of the row still applies).
- After writing, every written cell is read back and compared to the intended
  value; any mismatch makes the script exit nonzero.

Spreadsheet-id resolution order: input JSON `spreadsheet_id` → `--spreadsheet-id`
→ env `GOOGLE_SHEET_ID` → `job_finder.config` / `config_local` → built-in default.
Credentials: `service_account.json` at the repo root (override with
`--service-account` or env `GOOGLE_SERVICE_ACCOUNT_FILE`). Secrets are never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

DEFAULT_TERMINAL_STATUSES = {"Closed", "Resume Send", "Resume Reject"}
# Never overwritten if already nonblank, regardless of what the update asks.
PROTECTED_IF_SET = {"cover_letter_path"}
FALLBACK_SPREADSHEET_ID = "1lfYlHw_W9YzkFfE6IQZEnHTbORHBjAZ-p2-3F_AyKKQ"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def find_repo_root() -> str:
    """Walk up from cwd, then from this file, to find the dir holding service_account.json."""
    for start in (os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
        cur = start
        while True:
            if os.path.isfile(os.path.join(cur, "service_account.json")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    # Fall back to cwd; credential loading will raise a clear error if missing.
    return os.getcwd()


def resolve_spreadsheet_id(cli_id: str | None, json_id: str | None, repo_root: str) -> str:
    if json_id:
        return json_id
    if cli_id:
        return cli_id
    if os.getenv("GOOGLE_SHEET_ID"):
        return os.environ["GOOGLE_SHEET_ID"]
    # Try the project's own config modules without importing side effects heavily.
    sys.path.insert(0, repo_root)
    for mod in ("job_finder.config", "config_local"):
        try:
            m = __import__(mod, fromlist=["GOOGLE_SHEET_ID"])
            val = getattr(m, "GOOGLE_SHEET_ID", "") or ""
            if val:
                return val
        except Exception:
            pass
    return FALLBACK_SPREADSHEET_ID


def load_worksheet(spreadsheet_id: str, tab: str, sa_file: str) -> gspread.Worksheet:
    creds = Credentials.from_service_account_file(sa_file, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(spreadsheet_id).worksheet(tab)


def cell(row: list[str], idx: int) -> str:
    return row[idx].strip() if len(row) > idx else ""


def index_by_column(values: list[list[str]], idx: int) -> tuple[dict[str, int], set[str]]:
    """Map each nonblank value in a column to its row number; report duplicates."""
    first_seen: dict[str, int] = {}
    dupes: set[str] = set()
    for row_num, row in enumerate(values[1:], start=2):
        val = cell(row, idx)
        if not val:
            continue
        if val in first_seen:
            dupes.add(val)
        else:
            first_seen[val] = row_num
    return first_seen, dupes


def check_identity(values: list[list[str]], col_of: dict[str, int], row_num: int, expect: dict) -> list[dict]:
    """Return one entry per `expect` field that does not match the row as it stands."""
    if row_num < 2 or row_num > len(values):
        return [{"field": f, "want": str(v).strip(), "got": None, "why": "row out of range"}
                for f, v in expect.items()]
    row = values[row_num - 1]
    bad = []
    for field, want in expect.items():
        got = cell(row, col_of[field])
        if got != str(want).strip():
            bad.append({"field": field, "want": str(want).strip(), "got": got})
    return bad


def require_identity(updates: list[dict], allow_missing: bool) -> None:
    """Every update must assert the row's identity via expect.job_url."""
    if allow_missing:
        return
    offenders = [
        {"row": u.get("row"), "writes": sorted(k for k in u if k not in ("row", "expect"))}
        for u in updates
        if not str((u.get("expect") or {}).get("job_url", "")).strip()
    ]
    if offenders:
        raise SystemExit("\n".join([
            f"{len(offenders)} of {len(updates)} update(s) carry no expect.job_url. "
            "NOTHING WAS WRITTEN.",
            "Row numbers shift when rows are deleted from the tab, which would file these writes "
            "against the wrong jobs. Add the job_url you read for each row:",
            '    {"row": 1527, "job_status": "Suitable", "suitability_reason": "...",',
            '     "expect": {"job_url": "https://www.linkedin.com/jobs/view/..."}}',
            "",
            'Override only with the row in front of you: "allow_missing_expect": true.',
            "",
            json.dumps(offenders, indent=2, ensure_ascii=False),
        ]))


def resolve_identity(
    ws: gspread.Worksheet,
    values: list[list[str]],
    col_of: dict[str, int],
    updates: list[dict],
    remap: bool,
) -> tuple[list[dict], list[dict]]:
    """Verify every `expect` block before any write. Abort unless mismatches can be remapped."""
    asserted = [u for u in updates if u.get("expect")]
    if not asserted:
        return updates, []

    url_idx = col_of.get("job_url")
    url_index: dict[str, int] = {}
    url_dupes: set[str] = set()
    if remap:
        if url_idx is None:
            raise SystemExit(f"--remap needs a 'job_url' column; '{ws.title}' header has none.")
        url_index, url_dupes = index_by_column(values, url_idx)

    resolved: list[dict] = []
    remapped: list[dict] = []
    failures: list[dict] = []

    for u in updates:
        expect = u.get("expect")
        if not expect:
            resolved.append(u)
            continue

        row_num = int(u["row"])
        bad = check_identity(values, col_of, row_num, expect)
        if not bad:
            resolved.append(u)
            continue

        # Identity is wrong. Say where the job actually went, and remap if asked to.
        url = str(expect.get("job_url", "")).strip()
        found = url_index.get(url) if remap else None
        if remap and url and url not in url_dupes and found:
            moved = dict(u, row=found)
            still_bad = check_identity(values, col_of, found, expect)
            if still_bad:
                failures.append({"row": row_num, "mismatches": bad, "remap_target": found,
                                 "why": "remap target failed identity check"})
                continue
            remapped.append({"from": row_num, "to": found, "job_url": url})
            resolved.append(moved)
            continue

        why = "identity mismatch"
        if remap:
            if not url:
                why = "identity mismatch; cannot remap without expect.job_url"
            elif url in url_dupes:
                why = f"identity mismatch; job_url appears more than once in '{ws.title}'"
            else:
                why = f"identity mismatch; job_url not found in '{ws.title}' (row deleted?)"
        entry = {"row": row_num, "mismatches": bad, "why": why}
        if url and url_idx is not None and not remap:
            # Locate it anyway so the report says where the row went.
            lookup, dupes = index_by_column(values, url_idx)
            if url in lookup and url not in dupes:
                entry["found_at_row"] = lookup[url]
        failures.append(entry)

    if failures:
        lines = [
            f"Row identity check failed for {len(failures)} of {len(asserted)} asserted row(s) "
            f"in '{ws.title}'. NOTHING WAS WRITTEN.",
            "Rows have most likely shifted (deleted rows above them). Re-read the tab and "
            "re-map your decisions by job_url, or re-run with --remap.",
            "",
            json.dumps(failures, indent=2, ensure_ascii=False),
        ]
        raise SystemExit("\n".join(lines))

    return resolved, remapped


def apply_updates(
    ws: gspread.Worksheet,
    updates: list[dict],
    terminal: set[str],
    check: bool,
    allow_nonblank_result: bool = False,
    remap: bool = False,
    allow_missing_expect: bool = False,
) -> dict:
    # Cheap, sheet-independent check first: refuse unidentified writes outright.
    require_identity(updates, allow_missing_expect)

    values = ws.get_all_values()
    if not values:
        raise SystemExit("Worksheet is empty; nothing to update.")
    header = [h.strip() for h in values[0]]
    col_of = {name: i for i, name in enumerate(header)}

    # Validate every referenced column exists before touching anything.
    referenced = {k for u in updates for k in u if k not in ("row", "expect")}
    referenced |= {k for u in updates for k in (u.get("expect") or {})}
    missing = sorted(c for c in referenced if c not in col_of)
    if missing:
        raise SystemExit(
            f"Column(s) not found in '{ws.title}' header: {', '.join(missing)}. "
            "Create the column(s) to the right of the table first."
        )

    # Verify row identity before anything is written; aborts on mismatch.
    updates, remapped = resolve_identity(ws, values, col_of, updates, remap)
    asserted = [(int(u["row"]), u["expect"]) for u in updates if u.get("expect")]

    status_idx = col_of.get("job_status")
    result_idx = col_of.get("application_result")

    writes: list[dict] = []          # {"range","values"} for batch_update
    planned: list[dict] = []         # human-readable record of intended cell writes
    skipped_rows: list[dict] = []
    skipped_fields: list[dict] = []

    for u in sorted(updates, key=lambda x: x["row"]):
        row_num = int(u["row"])
        if row_num < 2 or row_num > len(values):
            skipped_rows.append({"row": row_num, "why": "row out of range"})
            continue
        current = values[row_num - 1]

        if not allow_nonblank_result and result_idx is not None and cell(current, result_idx):
            skipped_rows.append({"row": row_num, "why": f"application_result set ({cell(current, result_idx)!r})"})
            continue
        if status_idx is not None and cell(current, status_idx) in terminal:
            skipped_rows.append({"row": row_num, "why": f"terminal job_status ({cell(current, status_idx)!r})"})
            continue

        for col_name, new_val in u.items():
            if col_name in ("row", "expect"):
                continue
            idx = col_of[col_name]
            cur_val = cell(current, idx)
            if col_name in PROTECTED_IF_SET and cur_val:
                skipped_fields.append({"row": row_num, "field": col_name, "why": "already set", "current": cur_val})
                continue
            a1 = rowcol_to_a1(row_num, idx + 1)
            writes.append({"range": a1, "values": [[new_val]]})
            planned.append({"row": row_num, "field": col_name, "range": a1, "value": new_val})

    summary = {
        "tab": ws.title,
        "check": check,
        "cells_to_write": len(writes),
        "rows_touched": len({p["row"] for p in planned}),
        "rows_identity_checked": len(asserted),
        "rows_remapped": remapped,
        "skipped_rows": skipped_rows,
        "skipped_fields": skipped_fields,
        "mismatches": [],
    }

    if check or not writes:
        summary["planned"] = planned
        return summary

    ws.batch_update(writes, value_input_option="USER_ENTERED")

    # Verify read-back.
    after = ws.get_all_values()
    mismatches = []
    for p in planned:
        idx = col_of[p["field"]]
        got = cell(after[p["row"] - 1], idx)
        want = str(p["value"]).strip()
        if got != want:
            mismatches.append({"row": p["row"], "field": p["field"], "want": want, "got": got})

    # Re-verify identity: catches rows shifting between the pre-flight read and the write.
    for row_num, expect in asserted:
        for bad in check_identity(after, col_of, row_num, expect):
            mismatches.append({
                "row": row_num,
                "field": bad["field"],
                "want": bad["want"],
                "got": bad.get("got"),
                "why": "IDENTITY CHANGED AFTER WRITE — the sheet shifted mid-run and this "
                       "row was written to the wrong job. Re-map by job_url and re-apply.",
            })

    summary["mismatches"] = mismatches
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Mechanically apply pre-authored updates to a job-finder Google Sheet tab.")
    ap.add_argument("--input", required=True, help="Path to the updates JSON file.")
    ap.add_argument("--spreadsheet-id", default=None, help="Override spreadsheet id.")
    ap.add_argument("--service-account", default=None, help="Path to service_account.json.")
    ap.add_argument("--check", action="store_true", help="Dry run: print planned writes without applying.")
    ap.add_argument("--remap", action="store_true",
                    help="Relocate rows whose 'expect' identity fails, using expect.job_url, instead of aborting.")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    tab = payload.get("tab")
    updates = payload.get("updates")
    if not tab or not isinstance(updates, list) or not updates:
        raise SystemExit("Input JSON must contain a 'tab' string and a non-empty 'updates' list.")

    repo_root = find_repo_root()
    sa_file = (
        args.service_account
        or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        or os.path.join(repo_root, "service_account.json")
    )
    if not os.path.isfile(sa_file):
        raise SystemExit(f"Service account file not found: {sa_file}")

    spreadsheet_id = resolve_spreadsheet_id(args.spreadsheet_id, payload.get("spreadsheet_id"), repo_root)
    terminal = set(DEFAULT_TERMINAL_STATUSES) | set(payload.get("terminal_statuses", []))
    allow_nonblank_result = bool(payload.get("allow_nonblank_application_result", False))
    remap = bool(payload.get("remap_by_job_url", False)) or args.remap
    allow_missing_expect = bool(payload.get("allow_missing_expect", False))

    ws = load_worksheet(spreadsheet_id, tab, sa_file)
    summary = apply_updates(ws, updates, terminal, args.check, allow_nonblank_result, remap,
                            allow_missing_expect)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary["mismatches"] else 0


if __name__ == "__main__":
    sys.exit(main())
