import unittest

from spoof_liquidity_detector.providers.pendle import PendleProvider


class FakePendleProvider(PendleProvider):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _get(self, path, query=None, base_url=None):
        self.calls.append((path, query, base_url))
        if path == "/v1/limit-orders/incentive/configs":
            return {"configs": [{"chainId": 42161}]}
        if path == "/v1/limit-orders/incentive/user/aggregate":
            return {
                "currentEpochReward": 2.0,
                "userMakingAmountUsdIncentivized": 100.0,
            }
        if path == "/v1/limit-orders/incentive/user/reward-history":
            return {
                "epochs": [
                    {
                        "startEpochDate": "2026-07-24T00:00:00.000Z",
                        "endEpochDate": "2026-07-31T00:00:00.000Z",
                        "markets": [
                            {
                                "chainId": 42161,
                                "myReward": 7.0,
                                "averageMakingOrderValueUsd": 100.0,
                            },
                            {
                                "chainId": 1,
                                "myReward": 99.0,
                                "averageMakingOrderValueUsd": 999.0,
                            },
                        ],
                    }
                ]
            }
        if path == "/v1/limit-orders" and query and query.get("skip", 0) > 0:
            return {"results": []}
        if path == "/v1/limit-orders" and query and query.get("isActive") == "true":
            return {
                "results": [
                    {
                        "id": "0xactive",
                        "maker": "0xmakerA",
                        "chainId": 42161,
                        "yt": "0xmarket",
                        "lnImpliedRate": "100000000000000000",
                        "createdAt": "2026-07-24T09:00:00.000Z",
                        "latestEventTimestamp": "2026-07-24T09:00:00.000Z",
                        "isActive": True,
                        "isCanceled": False,
                        "status": "FILLABLE",
                        "orderState": {"orderType": "LONG_YIELD", "notionalVolumeUSD": "1000"},
                    }
                ]
            }
        if path == "/v1/limit-orders" and query and query.get("isActive") == "false":
            return {
                "results": [
                    {
                        "id": "0xcancelled",
                        "maker": "0xmakerB",
                        "chainId": 42161,
                        "yt": "0xmarket",
                        "lnImpliedRate": "120000000000000000",
                        "createdAt": "2026-07-24T09:00:00.000Z",
                        "latestEventTimestamp": "2026-07-24T09:01:00.000Z",
                        "isActive": False,
                        "isCanceled": True,
                        "status": "CANCELED",
                        "orderFilledStatus": {"notionalVolume": "0"},
                        "orderState": {"orderType": "SHORT_YIELD", "notionalVolumeUSD": "1200"},
                    }
                ]
            }
        return {"results": []}


class PendleProviderTest(unittest.TestCase):
    def test_lists_incentive_configs(self):
        provider = FakePendleProvider()

        configs = provider.list_incentive_configs()

        self.assertEqual(configs, [{"chainId": 42161}])
        self.assertEqual(provider.calls[0], ("/v1/limit-orders/incentive/configs", None, None))

    def test_fetch_limit_orders_builds_query(self):
        provider = FakePendleProvider()

        provider.fetch_limit_orders(chain_id=42161, limit=5, is_active=False, maker="0xmaker")

        path, query, _base_url = provider.calls[0]
        self.assertEqual(path, "/v1/limit-orders")
        self.assertEqual(query["chainId"], 42161)
        self.assertEqual(query["limit"], 5)
        self.assertEqual(query["isActive"], "false")
        self.assertEqual(query["maker"], "0xmaker")

    def test_fetch_order_book_rejects_too_much_precision(self):
        provider = FakePendleProvider()

        with self.assertRaises(ValueError):
            provider.fetch_order_book(chain_id=42161, market="0xmarket", precision_decimal=4)

    def test_load_events_converts_live_orders_to_order_events(self):
        provider = FakePendleProvider()

        events = provider.load_events()

        self.assertEqual([event.order_id for event in events], ["0xactive", "0xcancelled", "0xcancelled"])
        self.assertEqual([event.event_type for event in events], ["open", "open", "cancel"])
        self.assertEqual(events[0].venue, "pendle")
        self.assertEqual(events[0].market, "0xmarket")
        self.assertEqual(events[0].price, 0.1)
        self.assertEqual(events[2].side, "sell")

    def test_historical_scan_requires_chain_id(self):
        provider = FakePendleProvider()
        provider.lookback_days = 30

        with self.assertRaises(ValueError):
            provider.load_events()

    def test_fetch_account_economics_uses_reward_history(self):
        provider = FakePendleProvider()
        provider.chain_id = 42161

        economics = provider.fetch_account_economics(["0xmakerA"])

        self.assertEqual(economics["0xmakerA"].subsidy, 7.0)
        self.assertEqual(economics["0xmakerA"].capital, 100.0)
        self.assertEqual(round(economics["0xmakerA"].annualized_return, 2), 3.65)

    def test_historical_scan_uses_core_resume_token_api(self):
        class HistoricalFakePendleProvider(FakePendleProvider):
            def _get(self, path, query=None, base_url=None):
                self.calls.append((path, query, base_url))
                if path == "/v2/limit-orders":
                    return {
                        "results": [
                            {
                                "id": "0xcore-live",
                                "maker": "0xmakerA",
                                "chainId": 42161,
                                "yt": "0xmarket",
                                "lnImpliedRate": "100000000000000000",
                                "createdAt": "2026-07-24T09:00:00.000Z",
                                "latestEventTimestamp": "2026-07-24T09:00:00.000Z",
                                "isActive": True,
                                "orderState": {"orderType": "LONG_YIELD", "notionalVolumeUSD": "1000"},
                            }
                        ]
                    }
                if path == "/v2/limit-orders/archived":
                    return {"results": []}
                return super()._get(path, query=query, base_url=base_url)

        provider = HistoricalFakePendleProvider()
        provider.chain_id = 42161
        provider.lookback_days = 30

        orders = provider.fetch_detection_orders()

        self.assertEqual([order["id"] for order in orders], ["0xcore-live"])
        self.assertEqual(provider.calls[0][0], "/v2/limit-orders")
        self.assertEqual(provider.calls[0][2], "https://api-v2.pendle.finance/core")


if __name__ == "__main__":
    unittest.main()
