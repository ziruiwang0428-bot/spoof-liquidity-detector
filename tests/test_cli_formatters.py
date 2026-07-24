import unittest

from spoof_liquidity_detector.cli import (
    _format_archive_table,
    _format_pendle_incentives,
    _format_pendle_order_book,
    _format_pendle_orders,
    _format_polymarket_markets,
    _format_polymarket_order_book,
)
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

    def test_formats_pendle_incentives(self):
        table = _format_pendle_incentives(
            [
                {
                    "chainId": 42161,
                    "marketAddress": "0xa8a0dea40174cfc30fea9e3a77f182ab33f46e25",
                    "impliedApy": "0.06512738980426347",
                    "long": {"range": "0.035"},
                    "estimatedApr": {"buyYtApr": "0.0123", "sellPtApr": "0.0456"},
                }
            ]
        )

        self.assertIn("42161", table)
        self.assertIn("0xa8a0de...6e25", table)
        self.assertIn("0.0651274", table)

    def test_formats_pendle_orders(self):
        table = _format_pendle_orders(
            [
                {
                    "id": "0xf1adf65f9e0674d069dfb17d00c44b1a",
                    "chainId": 42161,
                    "maker": "0x2e966c978e4ae08b93bf3e3e11b38d5b4c1c1444",
                    "status": "FILLABLE",
                    "isActive": True,
                    "isCanceled": False,
                    "latestEventTimestamp": "2026-07-24T07:15:37.000Z",
                    "orderState": {"orderType": "LONG_YIELD", "notionalVolumeUSD": "150.9075"},
                }
            ]
        )

        self.assertIn("LONG_YIELD", table)
        self.assertIn("FILLABLE", table)
        self.assertIn("150.907", table)

    def test_formats_pendle_order_book(self):
        table = _format_pendle_order_book(
            {
                "longYieldEntries": [{"impliedApy": "0.06335", "pySize": "10", "notionalSize": "11"}],
                "shortYieldEntries": [{"impliedApy": "0.07123", "pySize": "12", "notionalSize": "13"}],
            },
            top=1,
        )

        self.assertIn("long", table)
        self.assertIn("short", table)
        self.assertIn("0.06335", table)

    def test_formats_polymarket_markets(self):
        table = _format_polymarket_markets(
            [
                {
                    "id": "540817",
                    "question": "New Rihanna Album before GTA VI?",
                    "clobTokenIds": '["98022490269692409998126496127597032490334070080325855126491859374983463996227"]',
                    "bestBid": "0.50",
                    "bestAsk": "0.53",
                    "liquidityNum": "9893.5129",
                    "volume24hr": "408.611754",
                }
            ]
        )

        self.assertIn("540817", table)
        self.assertIn("New Rihanna Album", table)
        self.assertIn("980224", table)

    def test_formats_polymarket_order_book(self):
        table = _format_polymarket_order_book(
            {
                "asset_id": "98022490269692409998126496127597032490334070080325855126491859374983463996227",
                "timestamp": "1784883097483",
                "bids": [{"price": "0.50", "size": "4366.52"}],
                "asks": [{"price": "0.53", "size": "8.68"}],
            },
            top=1,
        )

        self.assertIn("bid", table)
        self.assertIn("ask", table)
        self.assertIn("4366.52", table)


if __name__ == "__main__":
    unittest.main()
