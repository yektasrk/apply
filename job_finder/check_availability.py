"""
check_availability.py - Mark closed job rows in Google Sheets.

Usage:
  python -m job_finder.check_availability
  python -m job_finder.check_availability --country denmark
  python -m job_finder.check_availability --tab Denmark --dry-run
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import email.utils
import html
import logging
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable

import gspread
from gspread.utils import rowcol_to_a1

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
CLOSED_VALUE = "Closed"
DEFAULT_RATE_LIMIT_COOLDOWN = 300
MAX_RATE_LIMIT_COOLDOWN = 1800
DEFAULT_WRITE_BATCH_SIZE = 100

OVERWRITABLE_STATUSES = {
    "",
    "false",
    "no",
    "yes",
    "suitable",
    "not suitable",
}

CLOSED_PHRASES = (
    "no longer accepting applications",
    "this job is no longer available",
    "job is no longer available",
    "job no longer available",
    "job posting is no longer active",
    "job posting has expired",
    "this job has expired",
    "job has expired",
    "position has been filled",
    "posting has expired",
    "application deadline has passed",
    "closed for applications",
)

LINKEDIN_JOB_PATH_RE = re.compile(r"/jobs/(?:view|collections/.+?/jobs)/([^/?#]+)")
LINKEDIN_JOB_PAGE_MARKER = 'data-semaphore-content-type="job"'
LINKEDIN_CTA_CONTAINER_RE = re.compile(
    r'<div\b[^>]*\bclass="[^"]*top-card-layout__cta-container[^"]*"[^>]*>'
    r"(.*?)</div>",
    re.DOTALL,
)
LINKEDIN_EMPTY_ACTION_REASON = "LinkedIn posting has an empty action area"
LINKEDIN_CONFIRMED_CLOSED_REASON = (
    "LinkedIn posting has an empty action area in both public responses"
)
SHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")
SHEET_GID_RE = re.compile(r"[?&#]gid=(\d+)")

try:
    import certifi
except ImportError:
    HTTPS_CONTEXT = ssl.create_default_context()
else:
    HTTPS_CONTEXT = ssl.create_default_context(cafile=certifi.where())


@dataclasses.dataclass(frozen=True)
class Availability:
    state: str
    reason: str

    @property
    def is_closed(self) -> bool:
        return self.state == "closed"


def _normalise_status(value: str) -> str:
    return value.strip().lower()


def _decode_page(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="ignore")
    return html.unescape(text).lower()


def _contains_closed_phrase(text: str) -> str | None:
    return next((phrase for phrase in CLOSED_PHRASES if phrase in text), None)


def _extract_linkedin_job_id(url: str) -> str | None:
    match = LINKEDIN_JOB_PATH_RE.search(url)
    if match:
        id_match = re.search(r"(\d+)$", match.group(1).rstrip("/"))
        if id_match:
            return id_match.group(1)

    for part in reversed(url.rstrip("/").split("/")):
        clean = part.split("?")[0]
        if clean.isdigit():
            return clean
    return None


def _extract_sheet_id(value: str) -> str:
    match = SHEET_ID_RE.search(value)
    if match:
        return match.group(1)
    return value


def _extract_sheet_gid(value: str) -> int | None:
    match = SHEET_GID_RE.search(value)
    if match:
        return int(match.group(1))
    return None


def _linkedin_job_has_empty_action_area(
    body: str,
    original_url: str,
    final_url: str,
) -> bool:
    """Return whether LinkedIn rendered a verified job with no action controls."""
    original_host = urllib.parse.urlparse(original_url).hostname or ""
    final_host = urllib.parse.urlparse(final_url).hostname or ""
    if not (
        (original_host == "linkedin.com" or original_host.endswith(".linkedin.com"))
        and (final_host == "linkedin.com" or final_host.endswith(".linkedin.com"))
    ):
        return False

    original_job_id = _extract_linkedin_job_id(original_url)
    final_job_id = _extract_linkedin_job_id(final_url)
    if not original_job_id or final_job_id != original_job_id:
        return False

    job_marker = f'urn:li:jobposting:{original_job_id}'
    is_linkedin_job_page = (
        LINKEDIN_JOB_PAGE_MARKER in body
        and job_marker in body
    )
    if not is_linkedin_job_page:
        return False

    match = LINKEDIN_CTA_CONTAINER_RE.search(body)
    if not match:
        return False

    action_html = re.sub(r"<!--.*?-->", "", match.group(1), flags=re.DOTALL)
    return not action_html.strip()


def _url_host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None

    clean = value.strip()
    try:
        return max(0.0, float(clean))
    except ValueError:
        pass

    try:
        retry_at = email.utils.parsedate_to_datetime(clean)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=datetime.UTC)

    now = datetime.datetime.now(datetime.UTC)
    return max(0.0, (retry_at - now).total_seconds())


def _cooldown_remaining(host: str, cooldowns: dict[str, float]) -> float:
    until = cooldowns.get(host, 0.0)
    remaining = until - time.monotonic()
    if remaining <= 0:
        cooldowns.pop(host, None)
        return 0.0
    return remaining


def _record_rate_limit(
    host: str,
    retry_after: str | None,
    cooldowns: dict[str, float],
    fallback_seconds: float,
) -> float:
    parsed_wait = _retry_after_seconds(retry_after)
    wait_seconds = fallback_seconds if parsed_wait is None else parsed_wait
    wait_seconds = max(0.0, min(wait_seconds, MAX_RATE_LIMIT_COOLDOWN))
    cooldowns[host] = time.monotonic() + wait_seconds
    return wait_seconds


def _request_url(url: str, timeout: int) -> tuple[int, str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout, context=HTTPS_CONTEXT) as response:
        body = response.read(500_000)
        final_url = response.geturl()
        return response.status, final_url, _decode_page(body)


def _classify_response(
    status: int,
    final_url: str,
    body: str,
    original_url: str,
) -> Availability:
    if status in {404, 410}:
        return Availability("closed", f"HTTP {status}")
    if status in {401, 403, 429, 999}:
        return Availability("unknown", f"HTTP {status}")

    phrase = _contains_closed_phrase(body)
    if phrase:
        return Availability("closed", f"matched phrase: {phrase!r}")

    if _linkedin_job_has_empty_action_area(body, original_url, final_url):
        return Availability("unknown", LINKEDIN_EMPTY_ACTION_REASON)

    original_linkedin_id = _extract_linkedin_job_id(original_url)
    final_linkedin_id = _extract_linkedin_job_id(final_url)
    if (
        original_linkedin_id
        and final_linkedin_id
        and original_linkedin_id != final_linkedin_id
    ):
        return Availability("unknown", "redirected to a different LinkedIn job")

    if 200 <= status < 400:
        return Availability("active", f"HTTP {status}")
    return Availability("unknown", f"HTTP {status}")


def check_job_url(
    url: str,
    timeout: int,
    rate_limit_cooldowns: dict[str, float] | None = None,
    rate_limit_cooldown: float = DEFAULT_RATE_LIMIT_COOLDOWN,
) -> Availability:
    if rate_limit_cooldowns is None:
        rate_limit_cooldowns = {}

    linkedin_job_id = _extract_linkedin_job_id(url)
    urls_to_try = []
    if linkedin_job_id:
        urls_to_try.append(
            f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{linkedin_job_id}"
        )
    urls_to_try.append(url)

    last_closed: Availability | None = None
    last_unknown: Availability | None = None
    linkedin_empty_action_responses = 0
    for candidate_url in urls_to_try:
        host = _url_host(candidate_url)
        remaining = _cooldown_remaining(host, rate_limit_cooldowns)
        if remaining:
            if last_unknown is None:
                last_unknown = Availability(
                    "unknown",
                    f"rate limited: {host} cooldown active ({remaining:.0f}s remaining)",
                )
            continue

        try:
            status, final_url, body = _request_url(candidate_url, timeout)
        except urllib.error.HTTPError as error:
            try:
                body = _decode_page(error.read(500_000))
            except Exception:
                body = ""
            availability = _classify_response(error.code, error.url, body, url)
            if error.code == 429:
                wait_seconds = _record_rate_limit(
                    host,
                    error.headers.get("Retry-After"),
                    rate_limit_cooldowns,
                    rate_limit_cooldown,
                )
                availability = Availability(
                    "unknown",
                    f"HTTP 429; cooling down {host} for {wait_seconds:.0f}s",
                )
        except urllib.error.URLError as error:
            availability = Availability("unknown", f"request failed: {error.reason}")
        except TimeoutError:
            availability = Availability("unknown", "request timed out")
        except OSError as error:
            availability = Availability("unknown", f"request failed: {error}")
        else:
            availability = _classify_response(status, final_url, body, url)

        if availability.state == "active":
            return availability
        if availability.state == "closed":
            last_closed = availability
            continue
        if availability.reason == LINKEDIN_EMPTY_ACTION_REASON:
            linkedin_empty_action_responses += 1
        last_unknown = availability

    if (
        linkedin_job_id
        and len(urls_to_try) == 2
        and linkedin_empty_action_responses == len(urls_to_try)
    ):
        return Availability("closed", LINKEDIN_CONFIRMED_CLOSED_REASON)

    return last_closed or last_unknown or Availability(
        "unknown",
        "no availability signal",
    )


def _sheet() -> gspread.Spreadsheet:
    return sheets.get_spreadsheet()


def _target_tabs(
    spreadsheet: gspread.Spreadsheet,
    args: argparse.Namespace,
) -> list[gspread.Worksheet]:
    if args.gid is not None:
        return [
            worksheet
            for worksheet in spreadsheet.worksheets()
            if worksheet.id == args.gid
        ]

    if args.tab:
        return [spreadsheet.worksheet(args.tab)]

    if args.country:
        try:
            tab_name = config.COUNTRIES[args.country.lower()]["sheet_tab"]
        except KeyError:
            available = ", ".join(sorted(config.COUNTRIES))
            raise SystemExit(f"Unknown country '{args.country}'. Available: {available}") from None
        return [spreadsheet.worksheet(tab_name)]

    configured_tabs = {
        country_config["sheet_tab"]
        for country_config in config.COUNTRIES.values()
    }
    return [
        worksheet
        for worksheet in spreadsheet.worksheets()
        if worksheet.title in configured_tabs
    ]


def _header_indexes(headers: Iterable[str]) -> dict[str, int]:
    return {
        str(header).strip(): index
        for index, header in enumerate(headers)
        if str(header).strip()
    }


def _can_overwrite(status: str, force: bool) -> bool:
    if force:
        return True
    return _normalise_status(status) in OVERWRITABLE_STATUSES


def _flush_updates(
    ws: gspread.Worksheet,
    args: argparse.Namespace,
    updates: list[dict],
    counts: dict[str, int],
) -> None:
    if not updates:
        return

    batch_size = len(updates)
    if args.dry_run:
        log.info(
            "%s: dry run; would update %d row(s) in this batch",
            ws.title,
            batch_size,
        )
    else:
        ws.batch_update(updates, value_input_option="RAW")
        log.info(
            "%s: updated %d row(s) to %s in this batch",
            ws.title,
            batch_size,
            args.closed_value,
        )

    counts["updated"] += batch_size
    updates.clear()


def _check_worksheet(ws: gspread.Worksheet, args: argparse.Namespace) -> dict[str, int]:
    values = ws.get_all_values()
    if not values:
        log.warning("%s: empty worksheet; skipped", ws.title)
        return {
            "rows": 0,
            "checked": 0,
            "active": 0,
            "closed": 0,
            "updated": 0,
            "unknown": 0,
            "protected": 0,
            "blank_url": 0,
        }

    headers = _header_indexes(values[0])
    missing = [column for column in (STATUS_COLUMN, URL_COLUMN) if column not in headers]
    if missing:
        raise SystemExit(f"{ws.title}: missing required column(s): {', '.join(missing)}")

    status_col = headers[STATUS_COLUMN]
    url_col = headers[URL_COLUMN]
    updates = []
    rate_limit_cooldowns: dict[str, float] = {}
    counts = {
        "rows": max(0, len(values) - 1),
        "checked": 0,
        "active": 0,
        "closed": 0,
        "updated": 0,
        "unknown": 0,
        "protected": 0,
        "blank_url": 0,
    }

    for sheet_row, row in enumerate(values[1:], start=2):
        status = row[status_col].strip() if len(row) > status_col else ""
        url = row[url_col].strip() if len(row) > url_col else ""
        if not url:
            counts["blank_url"] += 1
            continue
        if _normalise_status(status) == _normalise_status(args.closed_value):
            continue
        if not _can_overwrite(status, args.force):
            counts["protected"] += 1
            continue

        counts["checked"] += 1
        availability = check_job_url(
            url,
            args.timeout,
            rate_limit_cooldowns=rate_limit_cooldowns,
            rate_limit_cooldown=args.rate_limit_cooldown,
        )
        counts[availability.state] += 1

        title = (
            row[headers["title"]].strip()
            if "title" in headers and len(row) > headers["title"]
            else url
        )
        log.info(
            "%s row %d: %s - %s (%s)",
            ws.title,
            sheet_row,
            availability.state,
            title,
            availability.reason,
        )

        if availability.is_closed:
            updates.append(
                {
                    "range": rowcol_to_a1(sheet_row, status_col + 1),
                    "values": [[args.closed_value]],
                }
            )

        if counts["checked"] % args.write_batch_size == 0:
            _flush_updates(ws, args, updates, counts)

        if args.limit and counts["checked"] >= args.limit:
            break
        if args.sleep:
            time.sleep(args.sleep)

    _flush_updates(ws, args, updates, counts)

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check job URLs and mark closed jobs in Google Sheets."
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--country", help="Configured country key, e.g. denmark")
    target.add_argument("--tab", help="Exact worksheet/tab name")
    target.add_argument(
        "--gid",
        type=int,
        help="Worksheet gid from the Google Sheets URL",
    )
    parser.add_argument(
        "--sheet",
        help="Spreadsheet ID or full Google Sheets URL; defaults to GOOGLE_SHEET_ID",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP timeout per request in seconds",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Delay between checked rows",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum rows to check per worksheet; 0 means no limit",
    )
    parser.add_argument(
        "--rate-limit-cooldown",
        type=float,
        default=DEFAULT_RATE_LIMIT_COOLDOWN,
        help="Cooldown per host after HTTP 429, in seconds",
    )
    parser.add_argument(
        "--write-batch-size",
        type=int,
        default=DEFAULT_WRITE_BATCH_SIZE,
        help="Flush pending sheet updates after this many checked jobs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report rows that would be marked without editing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite terminal statuses too",
    )
    parser.add_argument(
        "--closed-value",
        default=CLOSED_VALUE,
        help="Value to write into job_status",
    )
    args = parser.parse_args()

    if args.write_batch_size < 1:
        parser.error("--write-batch-size must be at least 1")

    if args.sheet:
        config.GOOGLE_SHEET_ID = _extract_sheet_id(args.sheet)
        if args.gid is None and args.country is None and args.tab is None:
            args.gid = _extract_sheet_gid(args.sheet)

    if config.GOOGLE_SHEET_ID in {"", "YOUR_SHEET_ID"}:
        raise SystemExit("Set GOOGLE_SHEET_ID before running this script.")

    spreadsheet = _sheet()
    worksheets = _target_tabs(spreadsheet, args)
    if not worksheets:
        raise SystemExit("No matching worksheets found.")

    total = {
        "rows": 0,
        "checked": 0,
        "active": 0,
        "closed": 0,
        "updated": 0,
        "unknown": 0,
        "protected": 0,
        "blank_url": 0,
    }
    for ws in worksheets:
        counts = _check_worksheet(ws, args)
        for key, value in counts.items():
            total[key] = total.get(key, 0) + value

    log.info(
        "Done. rows=%d checked=%d active=%d closed=%d updated=%d unknown=%d protected=%d blank_url=%d",
        total["rows"],
        total["checked"],
        total["active"],
        total["closed"],
        total["updated"],
        total["unknown"],
        total["protected"],
        total["blank_url"],
    )


if __name__ == "__main__":
    main()
