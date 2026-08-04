import unittest
from argparse import Namespace

from job_finder.cleanup import _collect, _group_contiguous


HEADER = ["job_status", "application_result", "applied_at", "title", "job_url"]


class FakeWorksheet:
    title = "Denmark"

    def __init__(self, rows: list[list[str]]) -> None:
        self.values = [HEADER] + rows

    def get_all_values(self) -> list[list[str]]:
        return self.values


def _args(limit: int = 0) -> Namespace:
    return Namespace(limit=limit, dry_run=True)


def _row(status, title, url, result="", applied_at=""):
    return [status, result, applied_at, title, url]


class GroupContiguousTests(unittest.TestCase):
    def test_collapses_runs_into_spans(self) -> None:
        self.assertEqual(_group_contiguous([5, 6, 7, 10, 12, 13]), [(5, 7), (10, 10), (12, 13)])

    def test_sorts_before_grouping(self) -> None:
        self.assertEqual(_group_contiguous([9, 2, 3]), [(2, 3), (9, 9)])

    def test_empty(self) -> None:
        self.assertEqual(_group_contiguous([]), [])


class CollectTests(unittest.TestCase):
    def test_selects_only_the_wanted_status(self) -> None:
        ws = FakeWorksheet([
            _row("Not Suitable", "Rejected", "https://example.com/1"),
            _row("Suitable", "Keep me", "https://example.com/2"),
            _row("Closed", "Closed job", "https://example.com/3"),
            _row("", "Untriaged", "https://example.com/4"),
        ])
        selected, delete_only, counts = _collect(ws, _args(), "Not Suitable", set())

        self.assertEqual([s["row"] for s in selected], [2])
        self.assertEqual(delete_only, [])
        self.assertEqual(counts["candidates"], 1)

    def test_application_evidence_is_never_touched(self) -> None:
        ws = FakeWorksheet([
            _row("Not Suitable", "Has result", "https://example.com/1", result="Resume Reject"),
            _row("Not Suitable", "Has timestamp", "https://example.com/2",
                 applied_at="2026-07-24 15:30 Asia/Tehran"),
            _row("Not Suitable", "Clean", "https://example.com/3"),
        ])
        selected, delete_only, counts = _collect(ws, _args(), "Not Suitable", set())

        self.assertEqual([s["url"] for s in selected], ["https://example.com/3"])
        self.assertEqual(delete_only, [])
        self.assertEqual(counts["protected"], 2)

    def test_blank_url_rows_are_left_alone(self) -> None:
        # Without a job_url the row cannot be re-verified before deletion, so
        # there is no way to prove the right row is being removed.
        ws = FakeWorksheet([
            _row("Not Suitable", "No link", ""),
            _row("Not Suitable", "Has link", "https://example.com/1"),
        ])
        selected, delete_only, counts = _collect(ws, _args(), "Not Suitable", set())

        self.assertEqual([s["row"] for s in selected], [3])
        self.assertEqual(counts["blank_url"], 1)

    def test_already_archived_rows_are_deleted_not_rearchived(self) -> None:
        # The state an interrupted run leaves: appended to the archive, but the
        # delete never happened. The row must still leave the live sheet, and
        # must not get a second archive copy.
        ws = FakeWorksheet([
            _row("Not Suitable", "Stuck", "https://example.com/stuck"),
            _row("Not Suitable", "Fresh", "https://example.com/fresh"),
        ])
        selected, delete_only, counts = _collect(
            ws, _args(), "Not Suitable", {"https://example.com/stuck"}
        )

        self.assertEqual([s["url"] for s in selected], ["https://example.com/fresh"])
        self.assertEqual([s["url"] for s in delete_only], ["https://example.com/stuck"])
        self.assertEqual(counts["already_archived"], 1)
        self.assertEqual(counts["candidates"], 1)

    def test_limit_counts_both_lists(self) -> None:
        ws = FakeWorksheet([
            _row("Not Suitable", "Stuck", "https://example.com/stuck"),
            _row("Not Suitable", "Fresh", "https://example.com/fresh"),
            _row("Not Suitable", "Third", "https://example.com/third"),
        ])
        selected, delete_only, _ = _collect(
            ws, _args(limit=2), "Not Suitable", {"https://example.com/stuck"}
        )

        self.assertEqual(len(selected) + len(delete_only), 2)

    def test_record_carries_every_column(self) -> None:
        ws = FakeWorksheet([_row("Not Suitable", "Rejected", "https://example.com/1")])
        selected, _, _ = _collect(ws, _args(), "Not Suitable", set())

        self.assertEqual(set(selected[0]["record"]), set(HEADER))
        self.assertEqual(selected[0]["record"]["title"], "Rejected")


if __name__ == "__main__":
    unittest.main()
