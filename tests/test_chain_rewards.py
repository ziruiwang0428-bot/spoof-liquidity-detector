import unittest

from spoof_liquidity_detector.evidence.rewards import (
    DEFAULT_POLYMARKET_REWARD_DISTRIBUTORS,
    ERC20_TRANSFER_TOPIC,
    scan_erc20_reward_transfers,
)


class FakeRewardClient:
    def __init__(self):
        self.calls = []

    def get_logs(self, **kwargs):
        self.calls.append(kwargs)
        return [
            {
                "topics": [
                    ERC20_TRANSFER_TOPIC,
                    kwargs["topics"][1],
                    "0x" + "0" * 24 + "1" * 40,
                ],
                "data": hex(2_500_000),
            }
        ]


class ChainRewardsTest(unittest.TestCase):
    def test_defaults_include_current_liquidity_reward_distributor(self):
        self.assertIn("0x2c2795EA295d5Eb51F9121B728eD2eA4e936a709", DEFAULT_POLYMARKET_REWARD_DISTRIBUTORS)

    def test_aggregates_reward_transfers_by_recipient(self):
        client = FakeRewardClient()
        rows = scan_erc20_reward_transfers(
            client,
            token_contracts=["0x" + "2" * 40],
            distributor_addresses=["0x" + "3" * 40, "0x" + "4" * 40],
            from_block=100,
            to_block=200,
        )

        self.assertEqual(rows["0x" + "1" * 40], 5.0)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[0]["topics"][0], ERC20_TRANSFER_TOPIC)


if __name__ == "__main__":
    unittest.main()
