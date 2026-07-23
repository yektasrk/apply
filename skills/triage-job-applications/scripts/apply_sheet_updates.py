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

Input JSON schema
-----------------
    {
      "spreadsheet_id": "1lfY...",          # optional; see resolution order below
      "tab": "Germany",                      # required — worksheet/tab name
      "terminal_statuses": ["Closed", ...],  # optional; extends the default set
      "allow_nonblank_application_result": false,  # optional; see below
      "updates": [
        {"row": 1527, "job_status": "Suitable", "suitability_reason": "..."},
        {"row": 1529, "job_status": "Not Suitable", "suitability_reason": "..."},
        {"row": 1561, "cover_letter_path": "/abs/path/Company.md"}
      ]
    }

Every key in an update object other than "row" is a *column header name* from the
tab's header row (row 1). Columns are matched by name, so this works across tabs
with different schemas. A field naming a column that does not exist in the header
is a hard error (create the column first, e.g. `suitability_reason`).

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


def apply_updates(
    ws: gspread.Worksheet,
    updates: list[dict],
    terminal: set[str],
    check: bool,
    allow_nonblank_result: bool = False,
) -> dict:
    values = ws.get_all_values()
    if not values:
        raise SystemExit("Worksheet is empty; nothing to update.")
    header = [h.strip() for h in values[0]]
    col_of = {name: i for i, name in enumerate(header)}

    # Validate every referenced column exists before touching anything.
    referenced = {k for u in updates for k in u if k != "row"}
    missing = sorted(c for c in referenced if c not in col_of)
    if missing:
        raise SystemExit(
            f"Column(s) not found in '{ws.title}' header: {', '.join(missing)}. "
            "Create the column(s) to the right of the table first."
        )

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
            if col_name == "row":
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
    summary["mismatches"] = mismatches
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Mechanically apply pre-authored updates to a job-finder Google Sheet tab.")
    ap.add_argument("--input", required=True, help="Path to the updates JSON file.")
    ap.add_argument("--spreadsheet-id", default=None, help="Override spreadsheet id.")
    ap.add_argument("--service-account", default=None, help="Path to service_account.json.")
    ap.add_argument("--check", action="store_true", help="Dry run: print planned writes without applying.")
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

    ws = load_worksheet(spreadsheet_id, tab, sa_file)
    summary = apply_updates(ws, updates, terminal, args.check, allow_nonblank_result)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary["mismatches"] else 0


if __name__ == "__main__":
    sys.exit(main())
