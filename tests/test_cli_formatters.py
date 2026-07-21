import unittest

from spoof_liquidity_detector.cli import _format_archive_table
from spoof_liquidity_detector.providers import ArchiveSnapshot


class CliFormatterTest(unittest.TestCase):
    def test_formats_archive_snapshot_table(self):
        table = _format_archive_table(
            [
                ArchiveSnapshot(
                    venue="polymarket",
                    name="book_2026-07-21.parquet",
                    url="https://archive.pmxt.dev/Polymarket/v2/book_2026-07-21.parquet",
                    format="parquet",
                )
            ]
        )

        self.assertIn("polymarket", table)
        self.assertIn("book_2026-07-21.parquet", table)
        self.assertIn("parquet", table)


if __name__ == "__main__":
    unittest.main()
