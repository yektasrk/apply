import unittest
import urllib.error
from unittest import mock

from job_finder.check_availability import (
    LINKEDIN_CONFIRMED_CLOSED_REASON,
    LINKEDIN_EMPTY_ACTION_REASON,
    _classify_response,
    check_job_url,
)


LINKEDIN_URL = "https://www.linkedin.com/jobs/view/4374108909/"
LINKEDIN_API_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4374108909"
)


def _linkedin_page(cta: str) -> str:
    return f"""
        <div data-semaphore-content-type="job"
             data-semaphore-content-urn="urn:li:jobposting:4374108909">
          <div class="top-card-layout__cta-container">
            {cta}
          </div>
        </div>
    """


class ClassifyResponseTests(unittest.TestCase):
    def test_single_empty_linkedin_action_area_is_unknown(self) -> None:
        availability = _classify_response(
            200,
            LINKEDIN_API_URL,
            _linkedin_page(""),
            LINKEDIN_URL,
        )

        self.assertEqual(availability.state, "unknown")
        self.assertEqual(availability.reason, LINKEDIN_EMPTY_ACTION_REASON)

    def test_any_linkedin_action_control_keeps_job_active(self) -> None:
        availability = _classify_response(
            200,
            LINKEDIN_API_URL,
            _linkedin_page(
                '<button class="new-linkedin-action-class">Apply</button>'
            ),
            LINKEDIN_URL,
        )

        self.assertEqual(availability.state, "active")


class CheckJobUrlTests(unittest.TestCase):
    @mock.patch("job_finder.check_availability._request_url")
    def test_empty_action_area_on_both_responses_is_closed(self, request_url) -> None:
        request_url.side_effect = [
            (200, LINKEDIN_API_URL, _linkedin_page("")),
            (200, LINKEDIN_URL, _linkedin_page("")),
        ]

        availability = check_job_url(LINKEDIN_URL, timeout=15)

        self.assertEqual(availability.state, "closed")
        self.assertEqual(availability.reason, LINKEDIN_CONFIRMED_CLOSED_REASON)

    @mock.patch("job_finder.check_availability._request_url")
    def test_one_empty_response_and_one_failure_is_unknown(self, request_url) -> None:
        request_url.side_effect = [
            (200, LINKEDIN_API_URL, _linkedin_page("")),
            urllib.error.URLError("temporary failure"),
        ]

        availability = check_job_url(LINKEDIN_URL, timeout=15)

        self.assertEqual(availability.state, "unknown")

    def test_non_linkedin_page_without_apply_action_is_active(self) -> None:
        availability = _classify_response(
            200,
            "https://example.com/jobs/4374108909",
            _linkedin_page(""),
            "https://example.com/jobs/4374108909",
        )

        self.assertEqual(availability.state, "active")


if __name__ == "__main__":
    unittest.main()
