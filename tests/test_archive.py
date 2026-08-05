import unittest

from job_finder.archive import ARCHIVE_HEADER, _read_url_column
from job_finder.sheets import SHEET_COLUMNS


class FakeWorksheet:
    def __init__(self, header: list[str], column: list[str] | None = None) -> None:
        self.title = "Denmark"
        self.header = header
        self.column = column or []

    def row_values(self, _row: int) -> list[str]:
        return self.header

    def batch_get(self, _ranges: list[str]) -> list[list[list[str]]]:
        return [[[v] for v in self.column]]


class ArchiveHeaderTests(unittest.TestCase):
    def test_header_is_exactly_the_live_header(self) -> None:
        # The archive tabs are Google Sheets Tables copied from the live tabs. A
        # Table owns its header row and auto-renames any column written past its
        # definition to "Column N", so an archive-only column would silently
        # lose its name and take dedup down with it.
        self.assertEqual(ARCHIVE_HEADER, ["scraped_at"] + SHEET_COLUMNS)


class ReadUrlColumnTests(unittest.TestCase):
    def test_reads_urls_and_drops_blanks(self) -> None:
        ws = FakeWorksheet(ARCHIVE_HEADER, ["https://example.com/1", "", " https://x/2 "])
        self.assertEqual(_read_url_column(ws), ["https://example.com/1", "https://x/2"])

    def test_headerless_tab_is_skipped_quietly(self) -> None:
        # The archive spreadsheet's default Sheet1 is not an archive tab and
        # holds no URLs, so it must not look like a failure.
        self.assertEqual(_read_url_column(FakeWorksheet([])), [])

    def test_missing_job_url_raises_instead_of_reading_as_empty(self) -> None:
        # Reading a damaged tab as "nothing archived" is how dedup re-imported
        # 10 archived Denmark jobs on 2026-08-05.
        damaged = [c for c in ARCHIVE_HEADER if c != "job_url"]
        with self.assertRaises(RuntimeError) as caught:
            _read_url_column(FakeWorksheet(damaged))
        self.assertIn("job_url", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
