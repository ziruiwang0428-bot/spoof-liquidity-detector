import unittest
from pathlib import Path

from spoof_liquidity_detector.accounts import load_account_economics
from spoof_liquidity_detector.pipeline import DetectionPipeline
from spoof_liquidity_detector.providers import CsvOrderEventProvider


class AccountProfilerTest(unittest.TestCase):
    def test_account_profiles_rank_profitable_far_cancellers_first(self):
        provider = CsvOrderEventProvider(Path("data/sample_order_events.csv"))
        economics = load_account_economics(Path("data/sample_account_economics.csv"))
        profiles = DetectionPipeline(provider).run_accounts(economics=economics)

        self.assertEqual(profiles[0].maker, "0xAlpha")
        self.assertGreater(profiles[0].account_risk_score, 0.8)
        self.assertIn("avoids_execution_near_touch", profiles[0].reasons)
        self.assertIn("subsidy_positive_after_cost", profiles[0].reasons)
        self.assertGreater(profiles[0].annualized_return, 1.0)
        self.assertGreater(profiles[0].average_price_to_mid_ratio, 0.04)

    def test_account_profiles_keep_real_filled_maker_lower_risk(self):
        provider = CsvOrderEventProvider(Path("data/sample_order_events.csv"))
        economics = load_account_economics(Path("data/sample_account_economics.csv"))
        profiles = DetectionPipeline(provider).run_accounts(economics=economics)
        by_maker = {profile.maker: profile for profile in profiles}

        self.assertLess(by_maker["0xRealMM"].account_risk_score, by_maker["0xAlpha"].account_risk_score)
        self.assertLess(by_maker["0xRealMM"].net_profit, 0)


if __name__ == "__main__":
    unittest.main()
