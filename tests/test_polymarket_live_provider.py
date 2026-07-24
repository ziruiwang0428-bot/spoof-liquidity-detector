import unittest

from spoof_liquidity_detector.providers.polymarket import PolymarketLiveProvider


class FakePolymarketLiveProvider(PolymarketLiveProvider):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _get(self, base_url, path, query=None):
        self.calls.append((base_url, path, query))
        if path == "/markets":
            return [{"id": "540817"}]
        return {"bids": [], "asks": []}


class PolymarketLiveProviderTest(unittest.TestCase):
    def test_lists_gamma_markets(self):
        provider = FakePolymarketLiveProvider()

        markets = provider.list_markets(limit=5)

        self.assertEqual(markets, [{"id": "540817"}])
        base_url, path, query = provider.calls[0]
        self.assertEqual(base_url, "https://gamma-api.polymarket.com")
        self.assertEqual(path, "/markets")
        self.assertEqual(query["limit"], 5)
        self.assertEqual(query["active"], "true")

    def test_fetches_clob_order_book(self):
        provider = FakePolymarketLiveProvider()

        provider.fetch_order_book(token_id="123")

        base_url, path, query = provider.calls[0]
        self.assertEqual(base_url, "https://clob.polymarket.com")
        self.assertEqual(path, "/book")
        self.assertEqual(query["token_id"], "123")


if __name__ == "__main__":
    unittest.main()
