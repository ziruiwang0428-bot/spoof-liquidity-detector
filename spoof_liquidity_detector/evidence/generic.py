from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from spoof_liquidity_detector.evidence.evm import (
    EvmChainEvidenceClient,
    _address_from_topic,
    _data_words,
    _hex_to_int,
    _word_to_int,
)
from spoof_liquidity_detector.evidence.fills import summarize_chain_fills
from spoof_liquidity_detector.schema import ChainEventEvidence, ChainFillSummary

NotionalSource = Literal["maker", "taker", "max"]


@dataclass(frozen=True)
class GenericFillEventConfig:
    venue: str
    event_topic: str
    maker_topic_index: int = 2
    taker_topic_index: int = 3
    maker_amount_word: int = 2
    taker_amount_word: int = 3
    fee_word: int | None = 4
    notional_source: NotionalSource = "max"
    amount_decimals: int = 6


def scan_generic_evm_chain_fills(
    client: EvmChainEvidenceClient,
    *,
    contracts: list[str],
    config: GenericFillEventConfig,
    from_block: int,
    to_block: int | str = "latest",
    chunk_size: int | None = 10_000,
    rewards: dict[str, float] | None = None,
) -> list[ChainFillSummary]:
    logs = client.get_logs(
        addresses=contracts,
        from_block=from_block,
        to_block=to_block,
        chunk_size=chunk_size,
        topics=[config.event_topic.lower()],
    )
    return summarize_chain_fills(
        (event for log in logs if (event := decode_generic_fill_event(log, config))),
        venue=config.venue,
        chain_id=client.chain_id,
        amount_decimals=config.amount_decimals,
        rewards=rewards,
    )


def decode_generic_fill_event(log: dict, config: GenericFillEventConfig) -> ChainEventEvidence | None:
    topics = [str(topic).lower() for topic in log.get("topics", [])]
    if len(topics) <= max(config.maker_topic_index, config.taker_topic_index):
        return None
    if topics[0] != config.event_topic.lower():
        return None

    words = _data_words(log.get("data", ""))
    required_word_indexes = [config.maker_amount_word, config.taker_amount_word]
    if config.fee_word is not None:
        required_word_indexes.append(config.fee_word)
    if len(words) <= max(required_word_indexes):
        return None

    maker_amount = _word_to_int(words[config.maker_amount_word])
    taker_amount = _word_to_int(words[config.taker_amount_word])
    fee = _word_to_int(words[config.fee_word]) if config.fee_word is not None else 0

    return ChainEventEvidence(
        event_name="OrderFilled",
        order_hash=topics[1] if len(topics) > 1 else "",
        maker=_address_from_topic(topics[config.maker_topic_index]),
        contract=str(log.get("address") or "").lower(),
        block_number=_hex_to_int(log.get("blockNumber")) if log.get("blockNumber") is not None else None,
        transaction_hash=str(log.get("transactionHash") or "").lower(),
        log_index=_hex_to_int(log.get("logIndex")) if log.get("logIndex") is not None else None,
        taker=_address_from_topic(topics[config.taker_topic_index]),
        notional_volume=_select_notional(maker_amount, taker_amount, config.notional_source),
        fee_paid=fee,
    )


def _select_notional(maker_amount: int, taker_amount: int, source: NotionalSource) -> int:
    if source == "maker":
        return maker_amount
    if source == "taker":
        return taker_amount
    return max(maker_amount, taker_amount)
