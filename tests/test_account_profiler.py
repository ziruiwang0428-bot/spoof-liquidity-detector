import unittest
from pathlib import Path

from spoof_liquidity_detector.accounts import load_account_economics
from spoof_liquidity_detector.accounts.profiler import AccountProfiler
from spoof_liquidity_detector.pipeline import DetectionPipeline
from spoof_liquidity_detector.providers import CsvOrderEventProvider
from spoof_liquidity_detector.schema import AccountChainEvidence


class AccountProfilerTest(unittest.TestCase):
    def test_account_profiles_rank_profitable_far_cancellers_first(self):
        provider = CsvOrderEventProvider(Path("data/sample_order_events.csv"))
        economics = load_account_economics(Path("data/sample_account_economics.csv"))
        profiles = DetectionPipeline(provider).run_accounts(economics=economics)

        self.assertEqual(profiles[0].maker, "0xAlpha")
        self.assertGreater(profiles[0].account_risk_score, 0.8)
        self.assertIn("avoids_execution_near_touch", profiles[0].reasons)
        self.assertIn("subsidy_positive_after_cost", profiles[0].reasons)
        self.assertEqual(profiles[0].far_order_ratio, 1.0)
        self.assertGreater(profiles[0].annualized_return, 1.0)

    def test_account_profiles_keep_real_filled_maker_lower_risk(self):
        provider = CsvOrderEventProvider(Path("data/sample_order_events.csv"))
        economics = load_account_economics(Path("data/sample_account_economics.csv"))
        profiles = DetectionPipeline(provider).run_accounts(economics=economics)
        by_maker = {profile.maker: profile for profile in profiles}

        self.assertLess(by_maker["0xRealMM"].account_risk_score, by_maker["0xAlpha"].account_risk_score)
        self.assertLess(by_maker["0xRealMM"].net_profit, 0)

    def test_account_profiles_lock_risky_account_with_order_log_evidence(self):
        provider = CsvOrderEventProvider(Path("data/sample_order_events.csv"))
        economics = load_account_economics(Path("data/sample_account_economics.csv"))
        order_results = DetectionPipeline(provider).run()
        profiles = AccountProfiler().profile(
            order_results,
            economics=economics,
            chain_evidence={
                "0xAlpha": AccountChainEvidence(
                    maker="0xAlpha",
                    order_count=2,
                    confirmed_order_count=2,
                    matched_log_count=2,
                    fill_event_count=0,
                    filled_notional=0.0,
                    blocks=(42, 43),
                    contracts=("0x2222222222222222222222222222222222222222",),
                )
            },
        )
        by_maker = {profile.maker: profile for profile in profiles}

        self.assertTrue(by_maker["0xAlpha"].chain_locked)
        self.assertEqual(by_maker["0xAlpha"].chain_evidence_ratio, 1.0)
        self.assertIn("chain_order_log_matched", by_maker["0xAlpha"].reasons)
        self.assertIn("reward_without_chain_fills", by_maker["0xAlpha"].reasons)
        self.assertIn("chain_evidence_locked_account", by_maker["0xAlpha"].reasons)

    def test_account_profiles_flag_high_reward_per_chain_fill(self):
        provider = CsvOrderEventProvider(Path("data/sample_order_events.csv"))
        economics = load_account_economics(Path("data/sample_account_economics.csv"))
        order_results = DetectionPipeline(provider).run()
        profiles = AccountProfiler().profile(
            order_results,
            economics=economics,
            chain_evidence={
                "0xAlpha": AccountChainEvidence(
                    maker="0xAlpha",
                    order_count=2,
                    confirmed_order_count=2,
                    matched_log_count=2,
                    fill_event_count=1,
                    filled_notional=1000.0,
                    blocks=(42, 43),
                    contracts=("0x2222222222222222222222222222222222222222",),
                    event_counts={"OrderFilledV2": 1},
                )
            },
        )
        by_maker = {profile.maker: profile for profile in profiles}

        self.assertEqual(by_maker["0xAlpha"].chain_fill_event_count, 1)
        self.assertEqual(by_maker["0xAlpha"].chain_filled_notional, 1000.0)
        self.assertAlmostEqual(by_maker["0xAlpha"].reward_to_chain_fill_ratio, 0.82, places=2)
        self.assertIn("high_reward_per_chain_fill", by_maker["0xAlpha"].reasons)


if __name__ == "__main__":
    unittest.main()
