import unittest

from spoof_liquidity_detector.providers.archive import snapshots_from_directory_html
from spoof_liquidity_detector.providers.pendle import PendleProvider
from spoof_liquidity_detector.providers.polymarket import PolymarketProvider


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

        snapshots = snapshots_from_directory_html(html, "https://archive.pmxt.dev/Polymarket/v2/", "polymarket")

        self.assertEqual([item.name for item in snapshots], ["book_2026-07-08.parquet", "trades.csv"])
        self.assertEqual(snapshots[0].format, "parquet")
        self.assertEqual(snapshots[0].venue, "polymarket")
        self.assertEqual(snapshots[0].url, "https://archive.pmxt.dev/Polymarket/v2/book_2026-07-08.parquet")

    def test_pendle_provider_defaults_to_limit_order_app(self):
        provider = PendleProvider()

        self.assertEqual(provider.source_url, "https://app.pendle.finance/limit-order")

    def test_polymarket_provider_defaults_to_archive(self):
        provider = PolymarketProvider()

        self.assertEqual(provider.venue, "polymarket")
        self.assertEqual(provider.base_url, "https://archive.pmxt.dev/Polymarket/v2/")


if __name__ == "__main__":
    unittest.main()
