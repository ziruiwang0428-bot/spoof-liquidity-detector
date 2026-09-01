import unittest

from unittest.mock import patch

from spoof_liquidity_detector.ui_server import _observation_days, pendle_account_profiles, sample_account_profiles
from test_pendle_provider import FakePendleProvider


class UiServerTest(unittest.TestCase):
    def test_calculates_observation_days_from_chain_timestamps(self):
        class FakeClient:
            def block_timestamp(self, block):
                return {100: 1_000, 200: 87_400}[block]

        self.assertEqual(_observation_days(FakeClient(), 100, 200), 1.0)

    def test_loads_sample_account_profiles_for_dashboard(self):
        rows = sample_account_profiles(top=3)

        self.assertEqual(len(rows), 3)
        self.assertIn("maker", rows[0])
        self.assertIn("account_risk_score", rows[0])
        self.assertIn("far_order_ratio", rows[0])
        self.assertIsInstance(rows[0]["reasons"], list)

    @patch("spoof_liquidity_detector.ui_server.PendleProvider", FakePendleProvider)
    def test_loads_pendle_account_profiles_for_dashboard(self):
        rows = pendle_account_profiles(
            {
                "chain_id": ["42161"],
                "top": ["2"],
                "fetch_limit": ["10"],
                "lookback_days": ["0"],
            }
        )

        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["venue"], "pendle")
        self.assertIn("account_risk_score", rows[0])
        self.assertEqual(rows[0]["evidence_mode"], "api_behavior_and_rewards")


if __name__ == "__main__":
    unittest.main()
