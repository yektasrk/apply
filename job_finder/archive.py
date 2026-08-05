"""
archive.py — the archive spreadsheet: append not-suitable rows, read known URLs.

Not-suitable rows are copied here and then deleted from the live sheet, so this
file is the only remaining record of them. Two rules follow from that:

- Dedup must read this sheet. If it does not, the next scrape re-imports every
  job that was just archived. `get_archive_spreadsheet()` raises when
  `GOOGLE_ARCHIVE_SHEET_ID` is unset rather than degrading quietly.
- An append must be verified by read-back before the caller deletes the source
  row. Deletion is irreversible; a silent append failure would lose the row.

Tabs mirror the live sheet's country tabs, share their exact header, and are
created on first use. The header is deliberately identical: the archive tabs are
Google Sheets Tables, a Table owns its header row, and any column written past
the Table's definition gets silently auto-renamed to `Column N` — which on
2026-08-05 cost the Denmark tab its extra columns and let dedup re-import 10
archived jobs. Same columns as live, no such gap.
"""

import logging

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1
from tenacity import retry, retry_if_exception_type

from . import config
from . import sheets
from .retries import RETRY

log = logging.getLogger(__name__)

ARCHIVE_HEADER = ["scraped_at"] + sheets.SHEET_COLUMNS

DEFAULT_TAB_ROWS = 1000


def _column_letter(index_zero_based: int) -> str:
    return rowcol_to_a1(1, index_zero_based + 1).rstrip("1")


def get_archive_spreadsheet() -> gspread.Spreadsheet:
    if not config.GOOGLE_ARCHIVE_SHEET_ID:
        raise RuntimeError(
            "GOOGLE_ARCHIVE_SHEET_ID is not set. Dedup reads the archive sheet; "
            "without it every archived job would be re-imported on the next "
            "scrape. Set it before scraping."
        )
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes
    )
    client = gspread.authorize(creds)
    return client.open_by_key(config.GOOGLE_ARCHIVE_SHEET_ID)


def ensure_archive_tab(
    spreadsheet: gspread.Spreadsheet,
    tab_title: str,
) -> gspread.Worksheet:
    """Return the country tab, creating it with the archive header if missing."""
    try:
        ws = spreadsheet.worksheet(tab_title)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(
            title=tab_title,
            rows=DEFAULT_TAB_ROWS,
            cols=len(ARCHIVE_HEADER),
        )
        ws.append_row(ARCHIVE_HEADER, value_input_option="RAW")
        log.info("Created archive tab '%s'.", tab_title)
        return ws

    headers = [str(value).strip() for value in ws.row_values(1)]
    if not headers:
        ws.append_row(ARCHIVE_HEADER, value_input_option="RAW")
        return ws

    if sheets.DEDUP_COLUMN not in headers:
        raise RuntimeError(
            f"Archive tab '{tab_title}' has no '{sheets.DEDUP_COLUMN}' column. "
            f"Every other column is matched by name and may be absent, but "
            f"without this one an archived row cannot be deduped."
        )
    return ws


@retry(**RETRY, retry=retry_if_exception_type(gspread.exceptions.APIError))
def _read_url_column(ws: gspread.Worksheet) -> list[str]:
    """Fetch only the `job_url` column from a tab.

    Archived rows keep their full `description`, so reading whole rows here
    would pull megabytes just to collect URLs.
    """
    headers = [str(value).strip() for value in ws.row_values(1)]
    if not any(headers):
        # An empty tab (e.g. the spreadsheet's default Sheet1) is not an archive
        # tab and holds no URLs; skip it without crying wolf on every read.
        return []
    if sheets.DEDUP_COLUMN not in headers:
        # A tab that has a header but no job_url is damaged, and reading it as
        # "no archived URLs" is the worst possible answer: dedup would wave
        # through every job this tab was archived to protect. Fail loudly.
        raise RuntimeError(
            f"Archive tab '{ws.title}' has no '{sheets.DEDUP_COLUMN}' column. "
            f"Dedup cannot read it, so archived jobs would be re-imported on the "
            f"next scrape. Fix the header row before scraping."
        )

    letter = _column_letter(headers.index(sheets.DEDUP_COLUMN))
    (column,) = ws.batch_get([f"{letter}2:{letter}"])
    return [cell[0].strip() for cell in column if cell and cell[0].strip()]


def get_archived_urls(tab_title: str | None = None) -> set[str]:
    """Every archived `job_url`, optionally limited to one tab.

    Read in full rather than over a recent window. The read is a single column
    of one country's tab, so the whole history costs about as much as a slice of
    it, and a window can only ever under-include — which re-imports a dead job,
    the failure this module exists to prevent.

    `tab_title` limits the read to one country. Live dedup is per-tab, so
    scraping one country never needs the other eight tabs. A country with
    nothing archived yet simply has no tab, which reads as an empty set.
    """
    spreadsheet = get_archive_spreadsheet()
    worksheets = spreadsheet.worksheets()
    if tab_title is not None:
        worksheets = [ws for ws in worksheets if ws.title == tab_title]

    urls: set[str] = set()
    for ws in worksheets:
        urls.update(_read_url_column(ws))
    log.info("Found %d archived job URL(s).", len(urls))
    return urls


def _next_empty_row(ws: gspread.Worksheet, headers: list[str]) -> int:
    """First free row, measured by the `job_url` column.

    Rows reach the archive only via the cleanup CLI, which refuses to move a row
    with a blank `job_url` (it could not be verified before deletion). So this
    column's length is exactly the number of archived rows plus the header.
    """
    url_index = headers.index(sheets.DEDUP_COLUMN)
    filled = ws.col_values(url_index + 1)
    return max(len(filled), 1) + 1


def append_rows(tab_title: str, records: list[dict[str, str]]) -> list[str]:
    """Append records to a country tab and verify them by read-back.

    `records` map live-sheet column names to values; columns are matched by name
    so live and archive header order can differ. Returns the archived `job_url`s.
    Raises if the read-back does not match — the caller must not delete the
    source rows unless this returns cleanly.
    """
    if not records:
        return []

    spreadsheet = get_archive_spreadsheet()
    ws = ensure_archive_tab(spreadsheet, tab_title)
    headers = [str(value).strip() for value in ws.row_values(1)]

    values = [[str(record.get(column, "")) for column in headers] for record in records]

    start_row = _next_empty_row(ws, headers)
    end_row = start_row + len(values) - 1
    if end_row > ws.row_count:
        ws.resize(rows=end_row + DEFAULT_TAB_ROWS)
        log.info("Expanded archive tab '%s' to %d rows.", tab_title, end_row + DEFAULT_TAB_ROWS)

    last_letter = _column_letter(len(headers) - 1)
    target = f"A{start_row}:{last_letter}{end_row}"
    ws.batch_update([{"range": target, "values": values}], value_input_option="RAW")

    written = ws.get(target)
    mismatches = []
    for offset, intended in enumerate(values):
        actual = written[offset] if offset < len(written) else []
        for column_index, want in enumerate(intended):
            got = actual[column_index] if column_index < len(actual) else ""
            if str(got).strip() != str(want).strip():
                mismatches.append(
                    f"row {start_row + offset} col {headers[column_index]!r}: "
                    f"want {want[:40]!r}, got {got[:40]!r}"
                )
    if mismatches:
        raise RuntimeError(
            f"Archive read-back failed for '{tab_title}' "
            f"({len(mismatches)} mismatch(es)); source rows must NOT be deleted. "
            + "; ".join(mismatches[:5])
        )

    # ensure_archive_tab has already guaranteed this column exists.
    url_index = headers.index(sheets.DEDUP_COLUMN)
    log.info("Archived %d row(s) to '%s' (verified).", len(values), tab_title)
    return [row[url_index].strip() for row in values]
