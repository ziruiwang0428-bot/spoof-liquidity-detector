import unittest

from spoof_liquidity_detector.evidence.evm import EvmChainEvidenceClient, decode_pendle_limit_order_event


TX_HASH = "0x" + "a" * 64
ORDER_ID = "0x" + "b" * 64
MAKER = "0x1111111111111111111111111111111111111111"
TOKEN = "0x3333333333333333333333333333333333333333"
YT = "0x4444444444444444444444444444444444444444"
TAKER = "0x5555555555555555555555555555555555555555"
ORDER_FILLED_V2_TOPIC = "0x338a8c0dbb137e9c2510c7dd2b702f9355dbb562eeebea01aa7f46683f56ab06"
UNKNOWN_CANCEL_TOPIC = "0x" + "f" * 64


class FakeEvmChainEvidenceClient(EvmChainEvidenceClient):
    def __init__(self):
        super().__init__(chain_id=42161, rpc_url="http://rpc.example")

    def get_transaction_receipt(self, transaction_hash):
        self.transaction_hash = transaction_hash
        return {
            "status": "0x1",
            "blockNumber": "0x2a",
            "logs": [
                {
                    "address": "0x2222222222222222222222222222222222222222",
                    "blockNumber": "0x2a",
                    "transactionHash": TX_HASH,
                    "logIndex": "0x0",
                    "topics": [ORDER_FILLED_V2_TOPIC, ORDER_ID, _topic_address(YT)],
                    "data": _words(
                        _uint(2),
                        _address(TOKEN),
                        _uint(100),
                        _uint(95),
                        _uint(1),
                        _uint(1000),
                        _address(MAKER),
                        _address(TAKER),
                    ),
                }
            ],
        }

    def get_logs(self, *, addresses, from_block, to_block, chunk_size=None):
        self.log_query = (addresses, from_block, to_block, chunk_size)
        return [
            {
                "address": addresses[0],
                "blockNumber": "0x2b",
                "transactionHash": "0x" + "c" * 64,
                "logIndex": "0x1",
                "topics": [UNKNOWN_CANCEL_TOPIC, _topic_address(MAKER), ORDER_ID],
                "data": "0x" + MAKER.removeprefix("0x").rjust(64, "0"),
            }
        ]


class EvmChainEvidenceClientTest(unittest.TestCase):
    def test_reads_block_timestamp_from_rpc(self):
        client = EvmChainEvidenceClient(chain_id=137, rpc_url="http://rpc.example")
        calls = []

        def fake_rpc(method, params):
            calls.append((method, params))
            return {"timestamp": "0x64"}

        client._rpc = fake_rpc

        self.assertEqual(client.block_timestamp(42), 100)
        self.assertEqual(calls, [("eth_getBlockByNumber", ["0x2a", False])])

    def test_confirms_receipt_and_matching_log(self):
        client = FakeEvmChainEvidenceClient()

        evidence = client.confirm_order_payload(
            {
                "id": ORDER_ID,
                "maker": MAKER,
                "createdTransactionHash": TX_HASH,
            },
            venue="pendle",
        )

        self.assertTrue(evidence.confirmed)
        self.assertEqual(evidence.status, "confirmed_with_decoded_event")
        self.assertEqual(evidence.transaction_hashes, (TX_HASH,))
        self.assertEqual(evidence.confirmed_transaction_count, 1)
        self.assertEqual(evidence.matched_log_count, 1)
        self.assertEqual(evidence.blocks, (42,))
        self.assertEqual(evidence.events[0].event_name, "OrderFilledV2")
        self.assertEqual(evidence.events[0].maker, MAKER)
        self.assertEqual(evidence.events[0].taker, TAKER)
        self.assertEqual(client.transaction_hash, TX_HASH)

    def test_marks_missing_transaction_hash(self):
        client = FakeEvmChainEvidenceClient()

        evidence = client.confirm_order_payload({"id": ORDER_ID, "maker": MAKER}, venue="pendle")

        self.assertFalse(evidence.confirmed)
        self.assertEqual(evidence.status, "no_transaction_hash")
        self.assertEqual(evidence.transaction_hashes, ())

    def test_confirms_matching_event_log_without_transaction_hash(self):
        client = FakeEvmChainEvidenceClient()

        evidence = client.confirm_order_payload(
            {"id": ORDER_ID, "maker": MAKER},
            venue="pendle",
            event_contracts=["0x3333333333333333333333333333333333333333"],
            from_block=100,
            to_block="latest",
        )

        self.assertTrue(evidence.confirmed)
        self.assertEqual(evidence.status, "confirmed_with_decoded_event")
        self.assertEqual(evidence.matched_log_count, 1)
        self.assertEqual(evidence.blocks, (43,))
        self.assertEqual(evidence.events[0].event_name, "OrderCanceled")
        self.assertEqual(client.log_query, (["0x3333333333333333333333333333333333333333"], 100, "latest", 50000))

    def test_decodes_pendle_fill_event_with_order_hash_and_maker(self):
        event = decode_pendle_limit_order_event(
            {
                "address": "0x2222222222222222222222222222222222222222",
                "blockNumber": "0x2a",
                "transactionHash": TX_HASH,
                "logIndex": "0x0",
                "topics": [ORDER_FILLED_V2_TOPIC, ORDER_ID, _topic_address(YT)],
                "data": _words(
                    _uint(2),
                    _address(TOKEN),
                    _uint(100),
                    _uint(95),
                    _uint(1),
                    _uint(1000),
                    _address(MAKER),
                    _address(TAKER),
                ),
            },
            order_id=ORDER_ID,
            maker=MAKER,
        )

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.event_name, "OrderFilledV2")
        self.assertEqual(event.order_hash, ORDER_ID)
        self.assertEqual(event.maker, MAKER)
        self.assertEqual(event.yt, YT)
        self.assertEqual(event.token, TOKEN)
        self.assertEqual(event.taker, TAKER)
        self.assertEqual(event.notional_volume, 1000)

    def test_rejects_decoded_event_for_different_maker(self):
        event = decode_pendle_limit_order_event(
            {
                "topics": [UNKNOWN_CANCEL_TOPIC, _topic_address("0x9999999999999999999999999999999999999999"), ORDER_ID],
                "data": "0x",
            },
            order_id=ORDER_ID,
            maker=MAKER,
        )

        self.assertIsNone(event)


def _uint(value: int) -> str:
    return hex(value)[2:].rjust(64, "0")


def _address(value: str) -> str:
    return value.removeprefix("0x").rjust(64, "0")


def _topic_address(value: str) -> str:
    return "0x" + _address(value)


def _words(*values: str) -> str:
    return "0x" + "".join(values)


if __name__ == "__main__":
    unittest.main()
