from __future__ import annotations

from typing import Iterable

from spoof_liquidity_detector.evidence.evm import (
    EvmChainEvidenceClient,
    _address_from_topic,
    _data_words,
    _hex_to_int,
    _word_to_int,
)
from spoof_liquidity_detector.evidence.fills import summarize_chain_fills
from spoof_liquidity_detector.schema import ChainEventEvidence, ChainFillSummary

POLYMARKET_USDC_DECIMALS = 6

DEFAULT_POLYMARKET_EXCHANGE_CONTRACTS = {
    # Polygon mainnet: Polymarket CTFExchangeV2 and NegRiskCtfExchangeV2.
    137: [
        "0xe111180000d2663c0091e4f400237545b87b996b",
        "0xe2222d279d744050d28e00520010520000310f59",
    ],
}

POLYMARKET_ORDER_FILLED_TOPIC = "0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee"


def scan_polymarket_chain_fills(
    client: EvmChainEvidenceClient,
    *,
    contracts: list[str],
    from_block: int,
    to_block: int | str = "latest",
    chunk_size: int | None = 10_000,
    rewards: dict[str, float] | None = None,
) -> list[ChainFillSummary]:
    """Scan Polymarket exchange logs and aggregate decoded fill contribution by maker."""
    rewards = {_normalize_address(maker): reward for maker, reward in (rewards or {}).items()}
    logs = client.get_logs(
        addresses=contracts,
        from_block=from_block,
        to_block=to_block,
        chunk_size=chunk_size,
        topics=[POLYMARKET_ORDER_FILLED_TOPIC],
    )
    return summarize_polymarket_chain_fills(
        (event for log in logs if (event := decode_polymarket_fill_event(log))),
        chain_id=client.chain_id,
        rewards=rewards,
    )


def summarize_polymarket_chain_fills(
    events: Iterable[ChainEventEvidence],
    *,
    chain_id: int,
    rewards: dict[str, float] | None = None,
) -> list[ChainFillSummary]:
    return summarize_chain_fills(
        events,
        venue="polymarket",
        chain_id=chain_id,
        amount_decimals=POLYMARKET_USDC_DECIMALS,
        rewards=rewards,
    )


def decode_polymarket_fill_event(log: dict) -> ChainEventEvidence | None:
    topics = [str(topic).lower() for topic in log.get("topics", [])]
    if len(topics) < 4:
        return None
    if topics[0] != POLYMARKET_ORDER_FILLED_TOPIC:
        return None

    words = _data_words(log.get("data", ""))
    if len(words) < 5:
        return None

    maker = _address_from_topic(topics[2])
    taker = _address_from_topic(topics[3])
    maker_amount, taker_amount, fee = _decode_amounts(words)
    filled_notional = _collateral_amount(words, maker_amount, taker_amount)

    return ChainEventEvidence(
        event_name="OrderFilled",
        order_hash=topics[1],
        maker=maker,
        contract=str(log.get("address") or "").lower(),
        block_number=_hex_to_int(log.get("blockNumber")) if log.get("blockNumber") is not None else None,
        transaction_hash=str(log.get("transactionHash") or "").lower(),
        log_index=_hex_to_int(log.get("logIndex")) if log.get("logIndex") is not None else None,
        taker=taker,
        notional_volume=filled_notional,
        fee_paid=fee,
    )


def _decode_amounts(words: list[str]) -> tuple[int, int, int]:
    if _looks_like_v2_fill(words):
        return _word_to_int(words[2]), _word_to_int(words[3]), _word_to_int(words[4])
    return _word_to_int(words[2]), _word_to_int(words[3]), _word_to_int(words[4])


def _collateral_amount(words: list[str], maker_amount: int, taker_amount: int) -> int:
    if _looks_like_v2_fill(words):
        side = _word_to_int(words[0])
        return maker_amount if side == 0 else taker_amount

    maker_asset_id = _word_to_int(words[0])
    taker_asset_id = _word_to_int(words[1])
    if maker_asset_id == 0:
        return maker_amount
    if taker_asset_id == 0:
        return taker_amount
    return max(maker_amount, taker_amount)


def _looks_like_v2_fill(words: list[str]) -> bool:
    return len(words) >= 7 and _word_to_int(words[0]) in {0, 1}


def _normalize_address(value: str) -> str:
    return str(value).lower()
