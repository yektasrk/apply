"""
cleanup.py - Move not-suitable rows to the archive sheet, and purge closed rows.

Usage:
  python -m job_finder.cleanup --country denmark --archive-unsuitable --dry-run
  python -m job_finder.cleanup --country denmark --archive-unsuitable
  python -m job_finder.cleanup --tab Denmark --purge-closed --one-time-migration

Two separate operations, neither on by default:

--archive-unsuitable copies `Not Suitable` rows to the archive spreadsheet and
  then deletes them from the live sheet. Safe to run repeatedly: a row whose
  job_url is already archived is skipped rather than duplicated.

--purge-closed deletes `Closed` rows outright. It is a ONE-TIME MIGRATION for
  the backlog of closed rows that accumulated while the availability checker
  still overwrote every status. Afterwards the checker only touches `Suitable`
  rows, so a `Closed` row means a job you wanted and intend to keep — running
  this again would delete exactly those. Hence the explicit
  --one-time-migration flag.

Safety:
  - Rows carrying an application (Applied status, or a nonblank
    application_result / applied_at) are never touched by either operation.
  - Nothing is deleted until the archive append has been verified by read-back,
    and every target row's job_url is re-checked against the live sheet
    immediately before the delete.
  - Deletes run bottom-up in contiguous batches so row numbers below a delete
    stay valid while it proceeds.

Do NOT run this while a triage or submit session is in flight. Those workflows
address rows by absolute row number, and deleting rows shifts every row beneath.
Run it at a session boundary, and outside the scrape cron slots.
"""

from __future__ import annotations

import argparse
import logging

import gspread

from . import archive
from . import config
from . import sheets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

STATUS_COLUMN = "job_status"
URL_COLUMN = "job_url"
NOT_SUITABLE_VALUE = "Not Suitable"
CLOSED_VALUE = "Closed"
# Mirrors check_availability: any one of these means an application exists for
# the row even when job_status has not caught up.
APPLICATION_EVIDENCE_COLUMNS = ("application_result", "applied_at")


def _normalise(value: str) -> str:
    return value.strip().lower()


def _cell(row: list[str], index: int) -> str:
    return row[index].strip() if len(row) > index else ""


def _header_indexes(headers: list[str]) -> dict[str, int]:
    return {
        str(header).strip(): index
        for index, header in enumerate(headers)
        if str(header).strip()
    }


def _target_tabs(
    spreadsheet: gspread.Spreadsheet,
    args: argparse.Namespace,
) -> list[gspread.Worksheet]:
    if args.tab:
        return [spreadsheet.worksheet(args.tab)]
    if args.country:
        try:
            tab_name = config.COUNTRIES[args.country.lower()]["sheet_tab"]
        except KeyError:
            available = ", ".join(sorted(config.COUNTRIES))
            raise SystemExit(f"Unknown country '{args.country}'. Available: {available}") from None
        return [spreadsheet.worksheet(tab_name)]

    configured = {c["sheet_tab"] for c in config.COUNTRIES.values()}
    return [ws for ws in spreadsheet.worksheets() if ws.title in configured]


def _group_contiguous(row_numbers: list[int]) -> list[tuple[int, int]]:
    """Collapse sorted row numbers into (start, end) inclusive spans."""
    spans: list[tuple[int, int]] = []
    for row in sorted(row_numbers):
        if spans and row == spans[-1][1] + 1:
            spans[-1] = (spans[-1][0], row)
        else:
            spans.append((row, row))
    return spans


def _delete_rows(ws: gspread.Worksheet, row_numbers: list[int]) -> None:
    """Delete rows bottom-up so pending indexes stay valid as the grid shrinks."""
    spans = _group_contiguous(row_numbers)
    requests = [
        {
            "deleteDimension": {
                "range": {
                    "sheetId": ws.id,
                    "dimension": "ROWS",
                    "startIndex": start - 1,
                    "endIndex": end,
                }
            }
        }
        for start, end in reversed(spans)
    ]
    ws.spreadsheet.batch_update({"requests": requests})
    log.info("%s: deleted %d row(s) in %d span(s).", ws.title, len(row_numbers), len(spans))


def _verify_still_matches(ws: gspread.Worksheet, planned: list[tuple[int, str]]) -> None:
    """Re-read the tab and confirm every target row still holds the same job_url.

    Row numbers were computed from an earlier read. If anything wrote to the
    sheet in between, deleting by those numbers would destroy unrelated rows.
    The header is re-resolved from this same fresh read rather than reused, so a
    column that moved cannot silently shift what gets compared.
    """
    fresh = ws.get_all_values()
    if not fresh:
        raise SystemExit(f"{ws.title}: worksheet is empty; refusing to delete.")
    url_col = _header_indexes(fresh[0])[URL_COLUMN]
    mismatches = []
    for row_num, expected_url in planned:
        actual = _cell(fresh[row_num - 1], url_col) if row_num <= len(fresh) else "<missing>"
        if actual != expected_url:
            mismatches.append(f"row {row_num}: expected {expected_url[:50]!r}, found {actual[:50]!r}")
    if mismatches:
        raise SystemExit(
            f"{ws.title}: sheet changed since it was read; refusing to delete. "
            + "; ".join(mismatches[:5])
        )


def _collect(
    ws: gspread.Worksheet,
    args: argparse.Namespace,
    wanted_status: str,
    archived_urls: set[str] | None,
) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Find rows matching a status, skipping anything carrying an application.

    Returns (to_archive, delete_only, counts). `delete_only` holds rows whose
    job_url is already in the archive — the state an interrupted run leaves
    behind, where the append succeeded but the delete did not. Those must still
    be deleted from the live sheet, or they stay in both places forever; they
    just must not be archived a second time.
    """
    values = ws.get_all_values()
    counts = {"rows": max(0, len(values) - 1), "candidates": 0, "protected": 0,
              "already_archived": 0, "blank_url": 0}
    if not values:
        return [], [], counts

    headers = _header_indexes(values[0])
    for required in (STATUS_COLUMN, URL_COLUMN):
        if required not in headers:
            raise SystemExit(f"{ws.title}: missing required column '{required}'")

    header_names = [str(h).strip() for h in values[0]]
    status_col = headers[STATUS_COLUMN]
    url_col = headers[URL_COLUMN]
    evidence_cols = [headers[c] for c in APPLICATION_EVIDENCE_COLUMNS if c in headers]

    selected: list[dict] = []
    delete_only: list[dict] = []
    for row_num, row in enumerate(values[1:], start=2):
        status = _cell(row, status_col)
        if _normalise(status) != _normalise(wanted_status):
            continue

        # An application exists for this row even though job_status says
        # otherwise. Never archive or delete it. (An `Applied` status cannot
        # reach here — it never matches wanted_status — so these columns are
        # the guard that actually does work.)
        if any(_cell(row, index) for index in evidence_cols):
            counts["protected"] += 1
            continue

        url = _cell(row, url_col)
        if not url:
            # A row with no job_url cannot be re-verified against the sheet
            # before deletion, so there is no safe way to prove we are deleting
            # the row we meant to. Leave it alone.
            counts["blank_url"] += 1
            continue
        entry = {
            "row": row_num,
            "url": url,
            "record": {name: _cell(row, i) for i, name in enumerate(header_names) if name},
        }

        if archived_urls is not None and url in archived_urls:
            # Already in the archive from an interrupted run. Do not archive it
            # again, but it still has to leave the live sheet.
            counts["already_archived"] += 1
            delete_only.append(entry)
        else:
            counts["candidates"] += 1
            selected.append(entry)

        if args.limit and len(selected) + len(delete_only) >= args.limit:
            break

    return selected, delete_only, counts


def _archive_unsuitable(ws: gspread.Worksheet, args: argparse.Namespace) -> dict[str, int]:
    archived_urls = archive.get_archived_urls(tab_title=ws.title)
    selected, delete_only, counts = _collect(ws, args, NOT_SUITABLE_VALUE, archived_urls)
    counts["archived"] = 0
    counts["deleted"] = 0
    to_delete = selected + delete_only

    if not to_delete:
        log.info("%s: nothing to archive (%s).", ws.title, counts)
        return counts

    if args.dry_run:
        log.info(
            "%s: dry run; would archive %d row(s) and delete %d "
            "(%d already archived by an earlier run). First 5: %s",
            ws.title,
            len(selected),
            len(to_delete),
            len(delete_only),
            [(s["row"], s["record"].get("title", "")[:40]) for s in to_delete[:5]],
        )
        return counts

    if selected:
        archive.append_rows(ws.title, [s["record"] for s in selected], reason="not-suitable")
        counts["archived"] = len(selected)

    _verify_still_matches(ws, [(s["row"], s["url"]) for s in to_delete])
    _delete_rows(ws, [s["row"] for s in to_delete])
    counts["deleted"] = len(to_delete)
    return counts


def _purge_closed(ws: gspread.Worksheet, args: argparse.Namespace) -> dict[str, int]:
    selected, _, counts = _collect(ws, args, CLOSED_VALUE, None)
    counts["archived"] = 0
    counts["deleted"] = 0

    if not selected:
        log.info("%s: nothing to purge (%s).", ws.title, counts)
        return counts

    if args.dry_run:
        log.info(
            "%s: dry run; would DELETE %d closed row(s) with no archive copy. First 5: %s",
            ws.title,
            len(selected),
            [(s["row"], s["record"].get("title", "")[:40]) for s in selected[:5]],
        )
        return counts

    _verify_still_matches(ws, [(s["row"], s["url"]) for s in selected])
    _delete_rows(ws, [s["row"] for s in selected])
    counts["deleted"] = len(selected)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Archive not-suitable rows and purge closed rows from the job sheet.",
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--country", help="Configured country key, e.g. denmark")
    target.add_argument("--tab", help="Exact worksheet/tab name")
    parser.add_argument(
        "--archive-unsuitable",
        action="store_true",
        help="Copy Not Suitable rows to the archive sheet, then delete them here.",
    )
    parser.add_argument(
        "--purge-closed",
        action="store_true",
        help=(
            "Delete Closed rows outright, without archiving. One-time migration "
            "for the pre-existing backlog; requires --one-time-migration."
        ),
    )
    parser.add_argument(
        "--one-time-migration",
        action="store_true",
        help=(
            "Confirm you mean to purge closed rows. After the migration a Closed "
            "row is a job you wanted and are keeping, so this is not routine."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Report without writing.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum rows to act on per tab; 0 means no limit.",
    )
    args = parser.parse_args()

    if not args.archive_unsuitable and not args.purge_closed:
        parser.error("choose at least one of --archive-unsuitable / --purge-closed")
    if args.purge_closed and not args.one_time_migration:
        parser.error(
            "--purge-closed deletes rows with no archive copy and is a one-time "
            "migration; pass --one-time-migration to confirm"
        )
    if not config.GOOGLE_SHEET_ID:
        raise SystemExit("Set GOOGLE_SHEET_ID before running this script.")

    spreadsheet = sheets.get_spreadsheet()
    worksheets = _target_tabs(spreadsheet, args)
    if not worksheets:
        raise SystemExit("No matching worksheets found.")

    total: dict[str, int] = {}
    for ws in worksheets:
        for label, run in (
            ("archive", _archive_unsuitable if args.archive_unsuitable else None),
            ("purge", _purge_closed if args.purge_closed else None),
        ):
            if run is None:
                continue
            counts = run(ws, args)
            log.info("%s [%s]: %s", ws.title, label, counts)
            for key, value in counts.items():
                total[key] = total.get(key, 0) + value

    log.info("Done%s. %s", " (dry run)" if args.dry_run else "", total)


if __name__ == "__main__":
    main()
