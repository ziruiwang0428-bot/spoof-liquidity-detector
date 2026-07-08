import unittest

from spoof_liquidity_detector.providers.archive import snapshots_from_directory_html
from spoof_liquidity_detector.providers.pendle import PendleProvider


class ArchiveProviderTest(unittest.TestCase):
    def test_parses_archive_links_from_directory_listing(self):
        html = """
        <html>
          <body>
            <a href="../">parent</a>
            <a href="book_2026-07-08.parquet">book_2026-07-08.parquet</a>
            <a href="trades.csv">trades.csv</a>
            <a href="notes.txt">notes.txt</a>
          </body>
        </html>
        """

        snapshots = snapshots_from_directory_html(html, "https://archive.pmxt.dev/Polymarket/v2/", "pendle")

        self.assertEqual([item.name for item in snapshots], ["book_2026-07-08.parquet", "trades.csv"])
        self.assertEqual(snapshots[0].format, "parquet")
        self.assertEqual(snapshots[0].venue, "pendle")
        self.assertEqual(snapshots[0].url, "https://archive.pmxt.dev/Polymarket/v2/book_2026-07-08.parquet")

    def test_pendle_provider_defaults_to_user_supplied_archive(self):
        provider = PendleProvider()

        self.assertEqual(provider.venue, "pendle")
        self.assertEqual(provider.base_url, "https://archive.pmxt.dev/Polymarket/v2/")


if __name__ == "__main__":
    unittest.main()
