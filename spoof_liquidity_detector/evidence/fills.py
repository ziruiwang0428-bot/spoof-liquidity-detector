from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable

from spoof_liquidity_detector.schema import ChainEventEvidence, ChainFillSummary


def summarize_chain_fills(
    events: Iterable[ChainEventEvidence],
    *,
    venue: str,
    chain_id: int,
    amount_decimals: int = 6,
    rewards: dict[str, float] | None = None,
) -> list[ChainFillSummary]:
    rewards = {_normalize_address(maker): reward for maker, reward in (rewards or {}).items()}
    grouped: dict[str, list[ChainEventEvidence]] = defaultdict(list)
    for event in events:
        grouped[_normalize_address(event.maker)].append(event)

    rows: list[ChainFillSummary] = []
    for maker, maker_events in grouped.items():
        filled_notional = sum((event.notional_volume or 0) / 10**amount_decimals for event in maker_events)
        fee_paid = sum((event.fee_paid or 0) / 10**amount_decimals for event in maker_events)
        reward = rewards.get(maker, 0.0)
        rows.append(
            ChainFillSummary(
                venue=venue,
                chain_id=chain_id,
                maker=maker,
                fill_count=len(maker_events),
                filled_notional=filled_notional,
                fee_paid=fee_paid,
                reward=reward,
                reward_to_fill_ratio=reward_to_fill_ratio(reward, filled_notional, len(maker_events)),
                blocks=tuple(sorted({event.block_number for event in maker_events if event.block_number is not None})),
                contracts=tuple(sorted({event.contract for event in maker_events if event.contract})),
                transaction_hashes=tuple(dict.fromkeys(event.transaction_hash for event in maker_events if event.transaction_hash)),
            )
        )
    return sorted(rows, key=lambda row: (_sort_ratio(row.reward_to_fill_ratio), row.filled_notional), reverse=True)


def reward_to_fill_ratio(reward: float, filled_notional: float, fill_count: int) -> float:
    if reward <= 0:
        return 0.0
    if filled_notional > 0:
        return reward / filled_notional
    if fill_count > 0:
        return reward / fill_count
    return math.inf


def _sort_ratio(value: float) -> float:
    return 1e18 if value == math.inf else value


def _normalize_address(value: str) -> str:
    return str(value).lower()
