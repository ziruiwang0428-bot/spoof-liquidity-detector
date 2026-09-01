import unittest

from spoof_liquidity_detector.evidence.generic import GenericFillEventConfig, decode_generic_fill_event


TOPIC = "0x" + "f" * 64
ORDER_HASH = "0x" + "a" * 64
TX_HASH = "0x" + "b" * 64
MAKER = "0x1111111111111111111111111111111111111111"
TAKER = "0x2222222222222222222222222222222222222222"
CONTRACT = "0x3333333333333333333333333333333333333333"


class GenericEvmFillsTest(unittest.TestCase):
    def test_decodes_configured_fill_event(self):
        event = decode_generic_fill_event(
            {
                "address": CONTRACT,
                "blockNumber": "0x7b",
                "transactionHash": TX_HASH,
                "logIndex": "0x1",
                "topics": [TOPIC, ORDER_HASH, _topic_address(MAKER), _topic_address(TAKER)],
                "data": _words(_uint(9), _uint(8), _uint(1_000_000), _uint(2_000_000), _uint(10_000)),
            },
            GenericFillEventConfig(
                venue="other-market",
                event_topic=TOPIC,
                maker_amount_word=2,
                taker_amount_word=3,
                fee_word=4,
                notional_source="taker",
            ),
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.maker, MAKER)
        self.assertEqual(event.taker, TAKER)
        self.assertEqual(event.notional_volume, 2_000_000)
        self.assertEqual(event.fee_paid, 10_000)
        self.assertEqual(event.block_number, 123)


def _uint(value: int) -> str:
    return hex(value)[2:].rjust(64, "0")


def _topic_address(value: str) -> str:
    return "0x" + value.removeprefix("0x").rjust(64, "0")


def _words(*values: str) -> str:
    return "0x" + "".join(values)


if __name__ == "__main__":
    unittest.main()
