"""
archive.py — the archive spreadsheet: append not-suitable rows, read known URLs.

Not-suitable rows are copied here and then deleted from the live sheet, so this
file is the only remaining record of them. Two rules follow from that:

- Dedup must read this sheet. If it does not, the next scrape re-imports every
  job that was just archived. `get_archive_spreadsheet()` raises when
  `GOOGLE_ARCHIVE_SHEET_ID` is unset rather than degrading quietly.
- An append must be verified by read-back before the caller deletes the source
  row. Deletion is irreversible; a silent append failure would lose the row.

Tabs mirror the live sheet's country tabs and are created on first use. The
header is the live header plus `archived_at`, `archive_reason`, `source_tab`.
"""

import datetime
import logging
import math

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1
from tenacity import retry, retry_if_exception_type

from . import config
from . import sheets
from .retries import RETRY

log = logging.getLogger(__name__)

ARCHIVE_EXTRA_COLUMNS = ["archived_at", "archive_reason", "source_tab"]
ARCHIVE_HEADER = ["scraped_at"] + sheets.SHEET_COLUMNS + ARCHIVE_EXTRA_COLUMNS

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M UTC"
DEFAULT_TAB_ROWS = 1000
MIN_DEDUP_WINDOW_DAYS = 7


def dedup_window_days() -> int:
    """How far back dedup reads the archive.

    A scrape only returns postings newer than `HOURS_OLD`, so a job archived
    longer ago than that can never come back. Derived rather than hardcoded so
    the window cannot drift out of sync when `HOURS_OLD` changes.
    """
    return max(MIN_DEDUP_WINDOW_DAYS, math.ceil(config.HOURS_OLD / 24 * 1.5))


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime(TIMESTAMP_FORMAT)


def _parse_timestamp(value: str) -> datetime.datetime | None:
    try:
        parsed = datetime.datetime.strptime(value.strip(), TIMESTAMP_FORMAT)
    except (ValueError, AttributeError):
        return None
    return parsed.replace(tzinfo=datetime.UTC)


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

    missing = [column for column in ARCHIVE_EXTRA_COLUMNS if column not in headers]
    if missing:
        raise RuntimeError(
            f"Archive tab '{tab_title}' is missing required column(s): "
            f"{', '.join(missing)}. Add them to the right of the header row."
        )
    return ws


@retry(**RETRY, retry=retry_if_exception_type(gspread.exceptions.APIError))
def _read_url_and_timestamp_columns(ws: gspread.Worksheet) -> list[tuple[str, str]]:
    """Fetch only the `job_url` and `archived_at` columns from a tab.

    Archived rows keep their full `description`, so reading whole rows here
    would pull megabytes just to collect URLs.
    """
    headers = [str(value).strip() for value in ws.row_values(1)]
    if not any(headers):
        # An empty tab (e.g. the spreadsheet's default Sheet1) is not an archive
        # tab and holds no URLs; skip it without crying wolf on every read.
        return []
    if "job_url" not in headers or "archived_at" not in headers:
        log.warning("Archive tab '%s' is missing job_url/archived_at.", ws.title)
        return []

    url_letter = _column_letter(headers.index("job_url"))
    stamp_letter = _column_letter(headers.index("archived_at"))
    urls, stamps = ws.batch_get([f"{url_letter}2:{url_letter}", f"{stamp_letter}2:{stamp_letter}"])

    pairs = []
    for index in range(max(len(urls), len(stamps))):
        url = urls[index][0] if index < len(urls) and urls[index] else ""
        stamp = stamps[index][0] if index < len(stamps) and stamps[index] else ""
        pairs.append((url.strip(), stamp.strip()))
    return pairs


def get_archived_urls(
    window_days: int | None = None,
    tab_title: str | None = None,
) -> set[str]:
    """Archived `job_url`s, optionally limited to one tab and a recent window.

    `window_days=None` reads every archived row and is what the archiver uses to
    stay idempotent. Dedup passes a window so the read stays small.

    `tab_title` limits the read to one country. Live dedup is per-tab, so
    scraping one country never needs the other eight tabs. A country with
    nothing archived yet simply has no tab, which reads as an empty set.
    """
    spreadsheet = get_archive_spreadsheet()
    cutoff = None
    if window_days is not None:
        cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=window_days)

    worksheets = spreadsheet.worksheets()
    if tab_title is not None:
        worksheets = [ws for ws in worksheets if ws.title == tab_title]

    urls: set[str] = set()
    for ws in worksheets:
        for url, stamp in _read_url_and_timestamp_columns(ws):
            if not url:
                continue
            if cutoff is not None:
                archived_at = _parse_timestamp(stamp)
                # An unparseable timestamp is kept: over-including costs a
                # skipped duplicate, under-including re-imports a dead job.
                if archived_at is not None and archived_at < cutoff:
                    continue
            urls.add(url)
    log.info("Found %d archived job URL(s).", len(urls))
    return urls


def _next_empty_row(ws: gspread.Worksheet, headers: list[str]) -> int:
    """First free row, measured by the `archived_at` column.

    Every row this module writes sets `archived_at`, so its length is exactly
    the number of archived rows plus the header.
    """
    stamp_index = headers.index("archived_at")
    filled = ws.col_values(stamp_index + 1)
    return max(len(filled), 1) + 1


def append_rows(
    tab_title: str,
    records: list[dict[str, str]],
    reason: str,
) -> list[str]:
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
    archived_at = _now()

    values: list[list[str]] = []
    for record in records:
        row = []
        for column in headers:
            if column == "archived_at":
                row.append(archived_at)
            elif column == "archive_reason":
                row.append(reason)
            elif column == "source_tab":
                row.append(tab_title)
            else:
                row.append(str(record.get(column, "")))
        values.append(row)

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

    url_index = headers.index("job_url") if "job_url" in headers else None
    archived_urls = [row[url_index].strip() for row in values] if url_index is not None else []
    log.info("Archived %d row(s) to '%s' (verified).", len(values), tab_title)
    return archived_urls
