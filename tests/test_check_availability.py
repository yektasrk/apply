import unittest
import urllib.error
from argparse import Namespace
from unittest import mock

from job_finder.check_availability import (
    Availability,
    LINKEDIN_CONFIRMED_CLOSED_REASON,
    LINKEDIN_EMPTY_ACTION_REASON,
    _check_worksheet,
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


class FakeWorksheet:
    title = "United Kingdom"

    def __init__(self, values: list[list[str]]) -> None:
        self.values = values
        self.batch_updates: list[list[dict]] = []

    def get_all_values(self) -> list[list[str]]:
        return self.values

    def batch_update(self, updates: list[dict], value_input_option: str) -> None:
        self.assert_raw(value_input_option)
        self.batch_updates.append([dict(update) for update in updates])

    @staticmethod
    def assert_raw(value_input_option: str) -> None:
        if value_input_option != "RAW":
            raise AssertionError(f"unexpected value input option: {value_input_option}")


def _worksheet_args(*, dry_run: bool, write_batch_size: int) -> Namespace:
    return Namespace(
        closed_value="Closed",
        dry_run=dry_run,
        force=False,
        limit=0,
        rate_limit_cooldown=60,
        sleep=0,
        timeout=15,
        write_batch_size=write_batch_size,
    )


class CheckWorksheetTests(unittest.TestCase):
    @mock.patch("job_finder.check_availability.check_job_url")
    def test_writes_pending_updates_after_each_checked_batch(self, check_url) -> None:
        check_url.return_value = Availability("closed", "test closure")
        worksheet = FakeWorksheet(
            [["job_status", "title", "job_url"]]
            + [
                ["Not Suitable", f"Job {number}", f"https://example.com/{number}"]
                for number in range(1, 6)
            ]
        )

        counts = _check_worksheet(
            worksheet,
            _worksheet_args(dry_run=False, write_batch_size=2),
        )

        self.assertEqual([len(batch) for batch in worksheet.batch_updates], [2, 2, 1])
        self.assertEqual(
            [[update["range"] for update in batch] for batch in worksheet.batch_updates],
            [["A2", "A3"], ["A4", "A5"], ["A6"]],
        )
        self.assertEqual(counts["checked"], 5)
        self.assertEqual(counts["updated"], 5)

    @mock.patch("job_finder.check_availability.check_job_url")
    def test_dry_run_counts_batches_without_writing(self, check_url) -> None:
        check_url.return_value = Availability("closed", "test closure")
        worksheet = FakeWorksheet(
            [
                ["job_status", "title", "job_url"],
                ["Suitable", "Job 1", "https://example.com/1"],
                ["Suitable", "Job 2", "https://example.com/2"],
                ["Suitable", "Job 3", "https://example.com/3"],
            ]
        )

        counts = _check_worksheet(
            worksheet,
            _worksheet_args(dry_run=True, write_batch_size=2),
        )

        self.assertEqual(worksheet.batch_updates, [])
        self.assertEqual(counts["updated"], 3)

    @mock.patch("job_finder.check_availability.check_job_url")
    def test_applied_rows_are_skipped_even_with_force(self, check_url) -> None:
        check_url.return_value = Availability("closed", "test closure")
        worksheet = FakeWorksheet(
            [
                ["job_status", "title", "job_url"],
                ["Applied", "Already submitted", "https://example.com/applied"],
                ["Suitable", "Still eligible", "https://example.com/suitable"],
            ]
        )

        args = _worksheet_args(dry_run=False, write_batch_size=100)
        args.force = True
        counts = _check_worksheet(worksheet, args)

        self.assertEqual(
            [[update["range"] for update in batch] for batch in worksheet.batch_updates],
            [["A3"]],
        )
        self.assertEqual(counts["checked"], 1)
        self.assertEqual(counts["updated"], 1)
        self.assertEqual(counts["protected"], 1)


if __name__ == "__main__":
    unittest.main()
