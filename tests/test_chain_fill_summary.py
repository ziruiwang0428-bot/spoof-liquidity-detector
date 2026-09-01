import unittest

from spoof_liquidity_detector.evidence.fills import summarize_chain_fills
from spoof_liquidity_detector.schema import ChainEventEvidence


class ChainFillSummaryTest(unittest.TestCase):
    def test_summarizes_any_evm_fill_events_by_maker(self):
        rows = summarize_chain_fills(
            [
                ChainEventEvidence(
                    event_name="OrderFilled",
                    order_hash="0x" + "a" * 64,
                    maker="0x1111111111111111111111111111111111111111",
                    contract="0x2222222222222222222222222222222222222222",
                    block_number=100,
                    transaction_hash="0x" + "b" * 64,
                    log_index=1,
                    notional_volume=1_000_000,
                    fee_paid=10_000,
                ),
                ChainEventEvidence(
                    event_name="OrderFilled",
                    order_hash="0x" + "c" * 64,
                    maker="0x1111111111111111111111111111111111111111",
                    contract="0x2222222222222222222222222222222222222222",
                    block_number=101,
                    transaction_hash="0x" + "d" * 64,
                    log_index=2,
                    notional_volume=2_000_000,
                    fee_paid=20_000,
                ),
            ],
            venue="demo-venue",
            chain_id=1,
            amount_decimals=6,
            rewards={"0x1111111111111111111111111111111111111111": 0.3},
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].venue, "demo-venue")
        self.assertEqual(rows[0].fill_count, 2)
        self.assertEqual(rows[0].filled_notional, 3.0)
        self.assertEqual(rows[0].fee_paid, 0.03)
        self.assertAlmostEqual(rows[0].reward_to_fill_ratio, 0.1)
        self.assertEqual(rows[0].blocks, (100, 101))
        self.assertEqual(rows[0].risk_level, "high")
        self.assertGreaterEqual(rows[0].risk_score, 0.7)
        self.assertIn("high_reward_per_chain_fill", rows[0].reasons)

    def test_includes_reward_accounts_without_chain_fills(self):
        rows = summarize_chain_fills(
            [],
            venue="demo-venue",
            chain_id=1,
            rewards={"0x1111111111111111111111111111111111111111": 5.0},
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].fill_count, 0)
        self.assertEqual(rows[0].risk_level, "high")
        self.assertEqual(rows[0].reward_to_fill_ratio, float("inf"))
        self.assertIn("reward_without_chain_fills", rows[0].reasons)


if __name__ == "__main__":
    unittest.main()
