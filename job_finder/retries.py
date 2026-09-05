"""
retries.py — Shared tenacity retry config for the Google Sheets calls.
"""

import logging

import gspread
from tenacity import (
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

RETRY = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, min=5, max=60),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)

# The statuses where an identical retry may well succeed: Google's rate limit
# and its 5xx frontend errors. Everything else the Sheets API returns is a
# standing fault — 401 bad credentials, 403 sheet not shared with the service
# account, 404 wrong id — and fails the same way on every attempt, so retrying
# only buys ~15s of backoff before reporting the error it already knew.
TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def is_transient_api_error(exc: BaseException) -> bool:
    """True for a gspread APIError worth retrying.

    Read the status off the HTTP response, not off `APIError.code`: that field
    is parsed out of the response *body*, and gspread substitutes -1 whenever
    the body is not the JSON it expects. A 503 served as an HTML error page —
    exactly what a Google frontend outage returns — would then look like -1 and
    fall through as permanent.
    """
    if not isinstance(exc, gspread.exceptions.APIError):
        return False
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is None:
        status = getattr(exc, "code", None)
    return status in TRANSIENT_STATUS_CODES


# Spread into @retry as `@retry(**RETRY_TRANSIENT)`.
RETRY_TRANSIENT = {**RETRY, "retry": retry_if_exception(is_transient_api_error)}
