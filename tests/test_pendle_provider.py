import unittest

from spoof_liquidity_detector.providers.pendle import PendleProvider


class FakePendleProvider(PendleProvider):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _get(self, path, query=None):
        self.calls.append((path, query))
        if path == "/v1/limit-orders/incentive/configs":
            return {"configs": [{"chainId": 42161}]}
        return {"results": []}


class PendleProviderTest(unittest.TestCase):
    def test_lists_incentive_configs(self):
        provider = FakePendleProvider()

        configs = provider.list_incentive_configs()

        self.assertEqual(configs, [{"chainId": 42161}])
        self.assertEqual(provider.calls[0], ("/v1/limit-orders/incentive/configs", None))

    def test_fetch_limit_orders_builds_query(self):
        provider = FakePendleProvider()

        provider.fetch_limit_orders(chain_id=42161, limit=5, is_active=False, maker="0xmaker")

        path, query = provider.calls[0]
        self.assertEqual(path, "/v1/limit-orders")
        self.assertEqual(query["chainId"], 42161)
        self.assertEqual(query["limit"], 5)
        self.assertEqual(query["isActive"], "false")
        self.assertEqual(query["maker"], "0xmaker")

    def test_fetch_order_book_rejects_too_much_precision(self):
        provider = FakePendleProvider()

        with self.assertRaises(ValueError):
            provider.fetch_order_book(chain_id=42161, market="0xmarket", precision_decimal=4)


if __name__ == "__main__":
    unittest.main()
