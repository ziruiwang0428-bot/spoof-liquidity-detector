import unittest

from spoof_liquidity_detector.evidence.polymarket import (
    POLYMARKET_ORDER_FILLED_TOPIC,
    decode_polymarket_fill_event,
    summarize_polymarket_chain_fills,
)


ORDER_HASH = "0x" + "a" * 64
TX_HASH = "0x" + "b" * 64
MAKER = "0x1111111111111111111111111111111111111111"
TAKER = "0x2222222222222222222222222222222222222222"
CONTRACT = "0x3333333333333333333333333333333333333333"


class PolymarketChainEvidenceTest(unittest.TestCase):
    def test_decodes_v2_order_filled_event(self):
        event = decode_polymarket_fill_event(
            {
                "address": CONTRACT,
                "blockNumber": "0x64",
                "transactionHash": TX_HASH,
                "logIndex": "0x2",
                "topics": [POLYMARKET_ORDER_FILLED_TOPIC, ORDER_HASH, _topic_address(MAKER), _topic_address(TAKER)],
                "data": _words(
                    _uint(0),
                    _uint(42),
                    _uint(123_000_000),
                    _uint(50_000_000),
                    _uint(1_000_000),
                    _uint(0),
                    _uint(7),
                ),
            }
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.event_name, "OrderFilled")
        self.assertEqual(event.order_hash, ORDER_HASH)
        self.assertEqual(event.maker, MAKER)
        self.assertEqual(event.taker, TAKER)
        self.assertEqual(event.notional_volume, 123_000_000)
        self.assertEqual(event.fee_paid, 1_000_000)

    def test_summarizes_fills_by_maker_with_reward_ratio(self):
        event = decode_polymarket_fill_event(
            {
                "address": CONTRACT,
                "blockNumber": "0x64",
                "transactionHash": TX_HASH,
                "logIndex": "0x2",
                "topics": [POLYMARKET_ORDER_FILLED_TOPIC, ORDER_HASH, _topic_address(MAKER), _topic_address(TAKER)],
                "data": _words(
                    _uint(0),
                    _uint(42),
                    _uint(200_000_000),
                    _uint(80_000_000),
                    _uint(2_000_000),
                    _uint(0),
                    _uint(7),
                ),
            }
        )

        assert event is not None
        rows = summarize_polymarket_chain_fills([event], chain_id=137, rewards={MAKER: 10.0})

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].maker, MAKER)
        self.assertEqual(rows[0].fill_count, 1)
        self.assertEqual(rows[0].filled_notional, 200.0)
        self.assertEqual(rows[0].fee_paid, 2.0)
        self.assertAlmostEqual(rows[0].reward_to_fill_ratio, 0.05)

def _uint(value: int) -> str:
    return hex(value)[2:].rjust(64, "0")


def _topic_address(value: str) -> str:
    return "0x" + value.removeprefix("0x").rjust(64, "0")


def _words(*values: str) -> str:
    return "0x" + "".join(values)


if __name__ == "__main__":
    unittest.main()
