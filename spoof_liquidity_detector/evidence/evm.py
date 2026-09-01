from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen

from spoof_liquidity_detector.schema import ChainEventEvidence, ChainEvidence

DEFAULT_RPC_URLS = {
    1: "https://ethereum-rpc.publicnode.com",
    137: "https://polygon.publicnode.com",
    42161: "https://arb1.arbitrum.io/rpc",
}

PENDLE_EVENT_TOPICS = {
    # Pendle IPLimitRouter events. Unknown deployments can still be decoded by shape below.
    "0x338a8c0dbb137e9c2510c7dd2b702f9355dbb562eeebea01aa7f46683f56ab06": "OrderFilledV2",
}


class EvmChainEvidenceClient:
    """Small JSON-RPC client for confirming order evidence on EVM chains."""

    def __init__(self, chain_id: int, rpc_url: str | None = None, timeout_seconds: float = 30.0) -> None:
        self.chain_id = chain_id
        self.rpc_url = rpc_url or DEFAULT_RPC_URLS.get(chain_id)
        self.timeout_seconds = timeout_seconds
        if not self.rpc_url:
            raise ValueError(f"No default RPC URL configured for chain_id={chain_id}. Pass --rpc-url.")

    def confirm_order_payload(
        self,
        order: dict[str, Any],
        *,
        venue: str,
        event_contracts: list[str] | None = None,
        from_block: int | str | None = None,
        to_block: int | str = "latest",
        log_chunk_size: int | None = 50_000,
    ) -> ChainEvidence:
        order_id = str(order.get("id") or order.get("orderId") or "")
        maker = str(order.get("maker") or "")
        transaction_hashes = tuple(_extract_transaction_hashes(order))
        receipts = [self.get_transaction_receipt(tx_hash) for tx_hash in transaction_hashes]
        confirmed_receipts = [receipt for receipt in receipts if _receipt_success(receipt)]
        receipt_logs = [
            log
            for receipt in confirmed_receipts
            for log in receipt.get("logs", [])
        ]
        matched_events = [
            event for log in receipt_logs if (event := decode_pendle_limit_order_event(log, order_id=order_id, maker=maker))
        ]
        if event_contracts and order_id:
            for log in self.get_logs(
                addresses=event_contracts,
                from_block=from_block or "earliest",
                to_block=to_block,
                chunk_size=log_chunk_size,
            ):
                event = decode_pendle_limit_order_event(log, order_id=order_id, maker=maker)
                if event is not None:
                    matched_events.append(event)

        matched_events = _dedupe_events(matched_events)

        blocks = tuple(
            sorted(
                {
                    _hex_to_int(receipt.get("blockNumber"))
                    for receipt in confirmed_receipts
                    if receipt.get("blockNumber") is not None
                }
            )
        )
        log_blocks = {
            event.block_number
            for event in matched_events
            if event.block_number is not None
        }
        if log_blocks:
            blocks = tuple(sorted(set(blocks).union(log_blocks)))
        contracts = tuple(
            sorted(
                {
                    str(address).lower()
                    for address in (
                        [event.contract for event in matched_events]
                        + [
                            str(receipt_log.get("address") or "")
                            for receipt in confirmed_receipts
                            for receipt_log in receipt.get("logs", [])
                        ]
                    )
                    if address
                }
            )
        )

        if matched_events:
            status = "confirmed_with_decoded_event"
        elif not transaction_hashes:
            status = "no_transaction_hash"
        elif confirmed_receipts:
            status = "transaction_confirmed"
        else:
            status = "not_confirmed"

        return ChainEvidence(
            venue=venue,
            chain_id=self.chain_id,
            order_id=order_id,
            maker=maker,
            transaction_hashes=transaction_hashes,
            confirmed_transaction_count=len(confirmed_receipts),
            matched_log_count=len(matched_events),
            blocks=blocks,
            contracts=contracts,
            status=status,
            events=tuple(matched_events),
        )

    def get_transaction_receipt(self, transaction_hash: str) -> dict[str, Any]:
        return self._rpc("eth_getTransactionReceipt", [transaction_hash]) or {}

    def get_logs(
        self,
        *,
        addresses: list[str],
        from_block: int | str,
        to_block: int | str,
        chunk_size: int | None = None,
        topics: list[str | None] | None = None,
    ) -> list[dict[str, Any]]:
        if isinstance(from_block, int) and (isinstance(to_block, int) or to_block in {"latest", "safe", "finalized"}):
            end_block = self.block_number() if isinstance(to_block, str) else to_block
            if chunk_size and chunk_size > 0 and end_block >= from_block:
                rows: list[dict[str, Any]] = []
                start = from_block
                while start <= end_block:
                    end = min(start + chunk_size - 1, end_block)
                    rows.extend(self._get_logs_once(addresses=addresses, from_block=start, to_block=end, topics=topics))
                    start = end + 1
                return rows
        return self._get_logs_once(addresses=addresses, from_block=from_block, to_block=to_block, topics=topics)

    def block_number(self) -> int:
        return _hex_to_int(self._rpc("eth_blockNumber", []))

    def block_timestamp(self, block_number: int | str) -> int:
        block = self._rpc("eth_getBlockByNumber", [_block_param(block_number), False]) or {}
        timestamp = block.get("timestamp")
        if timestamp is None:
            raise RuntimeError(f"RPC returned no timestamp for block {block_number}")
        return _hex_to_int(timestamp)

    def _get_logs_once(
        self,
        *,
        addresses: list[str],
        from_block: int | str,
        to_block: int | str,
        topics: list[str | None] | None = None,
    ) -> list[dict[str, Any]]:
        params = {
            "address": addresses[0] if len(addresses) == 1 else addresses,
            "fromBlock": _block_param(from_block),
            "toBlock": _block_param(to_block),
        }
        if topics:
            params["topics"] = topics
        return list(self._rpc("eth_getLogs", [params]) or [])

    def _rpc(self, method: str, params: list[Any]) -> Any:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
        request = Request(
            self.rpc_url,
            data=body,
            headers={"content-type": "application/json", "user-agent": "spoof-liquidity-detector/0.1"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if "error" in payload:
            raise RuntimeError(f"RPC error from {method}: {payload['error']}")
        return payload.get("result")


def _extract_transaction_hashes(payload: dict[str, Any]) -> list[str]:
    hashes: list[str] = []

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, child_key)
            return
        if isinstance(value, list):
            for child_value in value:
                visit(child_value, key)
            return
        if not isinstance(value, str):
            return
        normalized_key = key.lower()
        if ("txhash" in normalized_key or "transactionhash" in normalized_key) and _looks_like_hash(value):
            hashes.append(value.lower())

    visit(payload)
    return list(dict.fromkeys(hashes))


def _receipt_success(receipt: dict[str, Any]) -> bool:
    return str(receipt.get("status", "")).lower() in {"0x1", "1"}


def decode_pendle_limit_order_event(
    log: dict[str, Any],
    *,
    order_id: str,
    maker: str,
) -> ChainEventEvidence | None:
    topics = [str(topic).lower() for topic in log.get("topics", [])]
    if not topics:
        return None

    expected_order_hash = _normalize_topic(order_id)
    expected_maker = _strip_hex(maker)
    if not expected_order_hash:
        return None

    event_name = PENDLE_EVENT_TOPICS.get(topics[0], f"UnknownLimitOrderEvent:{_short_topic(topics[0])}")
    order_hash = ""
    decoded_maker = ""
    order_type = None
    yt = ""
    token = ""
    taker = ""
    notional_volume = None

    if len(topics) >= 3 and topics[2] == expected_order_hash:
        order_hash = topics[2]
        decoded_maker = _address_from_topic(topics[1])
        event_name = "OrderCanceled" if event_name.startswith("UnknownLimitOrderEvent") else event_name
    elif len(topics) >= 2 and topics[1] == expected_order_hash:
        order_hash = topics[1]
        words = _data_words(log.get("data", ""))
        if len(topics) >= 3:
            yt = _address_from_topic(topics[2])
        if len(words) >= 8:
            order_type = _word_to_int(words[0])
            token = _address_from_word(words[1])
            notional_volume = _word_to_int(words[5])
            decoded_maker = _address_from_word(words[6])
            taker = _address_from_word(words[7])
            event_name = "OrderFilledV2" if event_name.startswith("UnknownLimitOrderEvent") else event_name
        if len(words) >= 8 and not _address_matches(decoded_maker, maker):
            decoded_maker = _address_from_word(words[7])
            event_name = "OrderPreSigned" if _address_matches(decoded_maker, maker) else event_name

    if order_hash != expected_order_hash:
        return None
    if expected_maker and not _address_matches(decoded_maker, maker):
        return None

    return ChainEventEvidence(
        event_name=event_name,
        order_hash=_topic_to_hash(order_hash),
        maker=decoded_maker,
        contract=str(log.get("address") or "").lower(),
        block_number=_hex_to_int(log.get("blockNumber")) if log.get("blockNumber") is not None else None,
        transaction_hash=str(log.get("transactionHash") or "").lower(),
        log_index=_hex_to_int(log.get("logIndex")) if log.get("logIndex") is not None else None,
        order_type=order_type,
        yt=yt,
        token=token,
        taker=taker,
        notional_volume=notional_volume,
    )


def _dedupe_events(events: list[ChainEventEvidence]) -> list[ChainEventEvidence]:
    deduped: list[ChainEventEvidence] = []
    seen: set[tuple[str, str, int | None]] = set()
    for event in events:
        key = (event.transaction_hash, event.contract, event.log_index)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped


def _log_matches_order(log: dict[str, Any], *, order_id: str, maker: str) -> bool:
    haystack = "".join(str(item) for item in log.get("topics", [])) + str(log.get("data", ""))
    normalized = haystack.lower().replace("0x", "")
    order_id_hex = _strip_hex(order_id)
    maker_hex = _strip_hex(maker)
    maker_topic_hex = maker_hex.rjust(64, "0") if _looks_like_address(maker) else ""
    if order_id_hex and maker_topic_hex:
        return order_id_hex in normalized and maker_topic_hex in normalized
    if order_id_hex:
        return order_id_hex in normalized
    return False


def _normalize_topic(value: str) -> str:
    text = _strip_hex(value)
    if not text:
        return ""
    return "0x" + text.rjust(64, "0")


def _topic_to_hash(value: str) -> str:
    return "0x" + _strip_hex(value).rjust(64, "0")


def _short_topic(value: str) -> str:
    text = str(value)
    return text if len(text) <= 14 else f"{text[:10]}...{text[-4:]}"


def _address_from_topic(value: str) -> str:
    return "0x" + _strip_hex(value)[-40:]


def _address_from_word(value: str) -> str:
    return "0x" + _strip_hex(value)[-40:]


def _word_to_int(value: str) -> int:
    return int(_strip_hex(value) or "0", 16)


def _data_words(value: object) -> list[str]:
    text = _strip_hex(str(value or ""))
    if not text:
        return []
    padded = text + "0" * ((64 - len(text) % 64) % 64)
    return ["0x" + padded[index : index + 64] for index in range(0, len(padded), 64)]


def _address_matches(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return _strip_hex(left)[-40:] == _strip_hex(right)[-40:]


def _looks_like_hash(value: str) -> bool:
    text = value.lower()
    return text.startswith("0x") and len(text) == 66 and all(char in "0123456789abcdef" for char in text[2:])


def _looks_like_address(value: str) -> bool:
    text = value.lower()
    return text.startswith("0x") and len(text) == 42 and all(char in "0123456789abcdef" for char in text[2:])


def _strip_hex(value: str) -> str:
    return value.lower().removeprefix("0x")


def _hex_to_int(value: object) -> int:
    if isinstance(value, int):
        return value
    return int(str(value), 16)


def _block_param(value: int | str) -> str:
    if isinstance(value, int):
        return hex(value)
    return value
