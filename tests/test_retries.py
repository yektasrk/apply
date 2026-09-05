import unittest

import gspread
from tenacity import retry, wait_none

from job_finder.retries import RETRY_TRANSIENT, is_transient_api_error


class FakeResponse:
    """Enough of a requests.Response for gspread.APIError to parse."""

    def __init__(self, status_code: int, payload: dict | None) -> None:
        self.status_code = status_code
        self.text = "<html>The service is currently unavailable.</html>"
        self._payload = payload

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("response body is not JSON")
        return self._payload


def api_error(status_code: int, *, json_body: bool = True) -> gspread.exceptions.APIError:
    payload = None
    if json_body:
        payload = {
            "error": {
                "code": status_code,
                "message": "The service is currently unavailable.",
                "status": "UNAVAILABLE",
            }
        }
    return gspread.exceptions.APIError(FakeResponse(status_code, payload))


class TransientPredicateTests(unittest.TestCase):
    def test_rate_limit_and_5xx_are_transient(self) -> None:
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                self.assertTrue(is_transient_api_error(api_error(status)))

    def test_html_bodied_503_is_still_transient(self) -> None:
        # gspread parses APIError.code out of the response body and substitutes
        # -1 when that body is not JSON. A Google frontend outage serves HTML,
        # so keying off .code instead of .status_code would read this outage as
        # permanent — the exact case this guard exists for.
        error = api_error(503, json_body=False)
        self.assertEqual(error.code, -1)
        self.assertTrue(is_transient_api_error(error))

    def test_standing_faults_are_not_retried(self) -> None:
        # 401/403/404 fail identically on every attempt; retrying them only
        # delays the report of a real credentials or sharing problem.
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                self.assertFalse(is_transient_api_error(api_error(status)))

    def test_non_api_errors_are_not_retried(self) -> None:
        self.assertFalse(is_transient_api_error(RuntimeError("boom")))


class RetryPolicyTests(unittest.TestCase):
    """Exercise the decorator itself, with the 5-60s backoff waited out."""

    def _counting_call(self, error: Exception):
        calls = []

        @retry(**RETRY_TRANSIENT)
        def opener() -> None:
            calls.append(1)
            raise error

        return opener.retry_with(wait=wait_none()), calls

    def test_transient_error_is_retried_then_reraised(self) -> None:
        opener, calls = self._counting_call(api_error(503))
        with self.assertRaises(gspread.exceptions.APIError):
            opener()
        self.assertEqual(len(calls), 3)

    def test_permanent_error_fails_on_the_first_attempt(self) -> None:
        opener, calls = self._counting_call(api_error(403))
        with self.assertRaises(gspread.exceptions.APIError):
            opener()
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
