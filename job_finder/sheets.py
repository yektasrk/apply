"""
sheets.py — Google Sheets read/write logic (shared by main.py and add_job.py)
"""

import datetime
import logging

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from tenacity import retry, retry_if_exception_type

from . import config
from .retries import RETRY

log = logging.getLogger(__name__)

SHEET_COLUMNS = [
    "job_status",
    "application_result",
    "title",
    "location",
    "company",
    "company_industry",
    "job_level",
    "job_type",
    "is_remote",
    "min_amount",
    "max_amount",
    "currency",
    "date_posted",
    "job_url",
    "description",
    "cover_letter_path",
    "suitability_reason",
    "applied_at",
    "application_notes",
]

DEDUP_COLUMN = "job_url"
ROW_MARKER_COLUMNS = ("scraped_at", "title", "job_url")


def get_spreadsheet() -> gspread.Spreadsheet:
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes
    )
    client = gspread.authorize(creds)
    return client.open_by_key(config.GOOGLE_SHEET_ID)


def get_worksheet() -> gspread.Worksheet:
    sheet = get_spreadsheet()
    return sheet.worksheet(config.GOOGLE_SHEET_TAB)


def ensure_header(ws: gspread.Worksheet) -> list[str]:
    """Validate the fixed sheet schema and return the worksheet's header order."""
    if ws.row_count == 0 or ws.cell(1, 1).value is None:
        ws.append_row(["scraped_at"] + SHEET_COLUMNS, value_input_option="RAW")
        log.info("Header row written.")
        return ["scraped_at"] + SHEET_COLUMNS

    headers = [str(value).strip() for value in ws.row_values(1)]
    missing = [column for column in SHEET_COLUMNS if column not in headers]
    if missing:
        raise RuntimeError(
            f"Worksheet '{ws.title}' is missing required column(s): {', '.join(missing)}. "
            "Run the one-time sheet schema migration before scraping."
        )
    return headers


@retry(**RETRY, retry=retry_if_exception_type(gspread.exceptions.APIError))
def get_existing_urls(ws: gspread.Worksheet) -> set[str]:
    all_values = ws.get_all_values()
    if len(all_values) < 2:
        return set()
    headers = [str(value).strip() for value in all_values[0]]
    try:
        url_col_index = headers.index(DEDUP_COLUMN)
    except ValueError:
        log.warning("Sheet is missing required '%s' column.", DEDUP_COLUMN)
        return set()
    existing = {
        row[url_col_index].strip()
        for row in all_values[1:]
        if len(row) > url_col_index and row[url_col_index].strip()
    }
    log.info("Found %d existing job URL(s) in sheet.", len(existing))
    return existing


def _build_rows(df: pd.DataFrame, headers: list[str]) -> list[list]:
    """Convert a cleaned DataFrame to sheet rows with a scraped_at prefix."""
    scraped_at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M UTC")
    columns = [column for column in headers if column != "scraped_at"]
    aligned = df.reindex(columns=columns, fill_value="")
    return [[scraped_at] + row.tolist() for _, row in aligned.iterrows()]


def _find_empty_rows(
    all_values: list[list[str]],
    row_count: int,
    size: int,
    headers: list[str],
) -> list[int]:
    """Return row numbers for the earliest empty job rows."""
    marker_indices = [
        headers.index(column)
        for column in ROW_MARKER_COLUMNS
        if column in headers
    ]
    rows: list[int] = []
    last_grid_row = max(len(all_values), row_count, 1)

    for row_num in range(2, last_grid_row + 1):
        row = all_values[row_num - 1] if row_num <= len(all_values) else []
        if not any(
            len(row) > index and str(row[index]).strip()
            for index in marker_indices
        ):
            rows.append(row_num)
            if len(rows) == size:
                return rows

    next_row = last_grid_row + 1
    while len(rows) < size:
        rows.append(next_row)
        next_row += 1
    return rows


def _write_rows(ws: gspread.Worksheet, rows: list[list], headers: list[str]) -> None:
    """Expand the grid if needed, then write rows into the earliest empty rows."""
    @retry(**RETRY, retry=retry_if_exception_type(gspread.exceptions.APIError))
    def _do_write() -> None:
        all_values = ws.get_all_values()
        target_rows = _find_empty_rows(all_values, ws.row_count, len(rows), headers)
        needed_rows = max(target_rows)
        if needed_rows > ws.row_count:
            ws.resize(rows=needed_rows + 100)
            log.info("Expanded sheet to %d rows.", needed_rows + 100)

        ws.batch_update(
            [
                {"range": f"A{row_num}", "values": [row]}
                for row_num, row in zip(target_rows, rows)
            ],
            value_input_option="USER_ENTERED",
        )

    try:
        _do_write()
        log.info("Wrote %d row(s) to Google Sheets.", len(rows))
    except gspread.exceptions.APIError as e:
        log.error("Google Sheets API error: %s", e.response.json())
        raise
    except Exception as e:
        log.error("Unexpected error writing to sheet: %s", e)
        raise


def _prepare_df(jobs: pd.DataFrame) -> pd.DataFrame:
    """Normalise a jobs DataFrame to exactly SHEET_COLUMNS."""
    df = jobs.copy()
    for col in SHEET_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[SHEET_COLUMNS].fillna("").astype(str)


def push_jobs(jobs: pd.DataFrame) -> tuple[int, int, pd.DataFrame]:
    """
    Append only new (non-duplicate) jobs to Google Sheets.
    Returns (rows_written, rows_skipped, new_jobs).
    """
    if jobs.empty:
        log.warning("No jobs to push.")
        return 0, 0, pd.DataFrame()

    ws = get_worksheet()
    headers = ensure_header(ws)

    existing_urls = get_existing_urls(ws)
    df = _prepare_df(jobs)

    before = len(df)
    df = df[~df[DEDUP_COLUMN].isin(existing_urls)]
    skipped = before - len(df)

    if skipped:
        log.info("Skipped %d duplicate(s) already in sheet.", skipped)
    if df.empty:
        log.info("No new jobs to write — all duplicates.")
        return 0, skipped, df

    _write_rows(ws, _build_rows(df, headers), headers)
    return len(df), skipped, df


def push_single(job: pd.Series) -> bool:
    """
    Add a single job Series to the sheet.
    Returns True if written, False if it was a duplicate.
    """
    ws = get_worksheet()
    headers = ensure_header(ws)

    job_url = str(job.get("job_url") or "")
    if job_url in get_existing_urls(ws):
        log.warning("Job already in sheet — skipping.")
        return False

    df = _prepare_df(pd.DataFrame([job]))
    _write_rows(ws, _build_rows(df, headers), headers)
    return True
