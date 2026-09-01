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
    suspicious_reward_to_fill_ratio: float = 0.05,
) -> list[ChainFillSummary]:
    reward_source_present = rewards is not None
    rewards = {_normalize_address(maker): reward for maker, reward in (rewards or {}).items()}
    grouped: dict[str, list[ChainEventEvidence]] = defaultdict(list)
    for event in events:
        grouped[_normalize_address(event.maker)].append(event)
    for maker in rewards:
        grouped.setdefault(maker, [])

    rows: list[ChainFillSummary] = []
    for maker, maker_events in grouped.items():
        filled_notional = sum((event.notional_volume or 0) / 10**amount_decimals for event in maker_events)
        fee_paid = sum((event.fee_paid or 0) / 10**amount_decimals for event in maker_events)
        reward = rewards.get(maker, 0.0)
        ratio = reward_to_fill_ratio(reward, filled_notional, len(maker_events))
        risk_score, risk_level, reasons = reward_fill_risk(
            reward,
            filled_notional,
            len(maker_events),
            suspicious_ratio=suspicious_reward_to_fill_ratio,
            reward_source_present=reward_source_present,
        )
        rows.append(
            ChainFillSummary(
                venue=venue,
                chain_id=chain_id,
                maker=maker,
                fill_count=len(maker_events),
                filled_notional=filled_notional,
                fee_paid=fee_paid,
                reward=reward,
                reward_to_fill_ratio=ratio,
                blocks=tuple(sorted({event.block_number for event in maker_events if event.block_number is not None})),
                contracts=tuple(sorted({event.contract for event in maker_events if event.contract})),
                transaction_hashes=tuple(dict.fromkeys(event.transaction_hash for event in maker_events if event.transaction_hash)),
                risk_score=risk_score,
                risk_level=risk_level,
                evidence_mode="reward_and_chain_fill" if reward_source_present else "chain_fill",
                reasons=reasons,
            )
        )
    return sorted(rows, key=lambda row: (row.risk_score, _sort_ratio(row.reward_to_fill_ratio), row.filled_notional), reverse=True)


def reward_to_fill_ratio(reward: float, filled_notional: float, fill_count: int) -> float:
    if reward <= 0:
        return 0.0
    if filled_notional > 0:
        return reward / filled_notional
    if fill_count > 0:
        return reward / fill_count
    return math.inf


def reward_fill_risk(
    reward: float,
    filled_notional: float,
    fill_count: int,
    *,
    suspicious_ratio: float = 0.05,
    reward_source_present: bool = True,
) -> tuple[float, str, tuple[str, ...]]:
    """Score a reward account using only reproducible reward and fill evidence."""
    if reward <= 0:
        if not reward_source_present:
            reasons = ("chain_fills_verified", "reward_evidence_missing") if fill_count else ("reward_evidence_missing",)
            return 0.0, "unscored", reasons
        reasons = ("chain_fills_verified", "no_reward_observed") if fill_count else ("no_reward_or_fill_observed",)
        return 0.05 if fill_count else 0.0, "low", reasons
    if fill_count == 0:
        return 0.95, "high", ("reward_verified", "reward_without_chain_fills")

    ratio = reward_to_fill_ratio(reward, filled_notional, fill_count)
    threshold = max(suspicious_ratio, 1e-12)
    relative_ratio = ratio / threshold
    risk_score = min(0.99, 0.2 + 0.5 * min(relative_ratio, 1.0) + 0.29 * max(relative_ratio - 1.0, 0.0))
    risk_score = round(risk_score, 4)
    if risk_score >= 0.7:
        level = "high"
    elif risk_score >= 0.4:
        level = "medium"
    else:
        level = "low"

    reasons = ["reward_verified", "chain_fills_verified"]
    if ratio >= threshold:
        reasons.append("high_reward_per_chain_fill")
    else:
        reasons.append("reward_supported_by_chain_fills")
    return risk_score, level, tuple(reasons)


def _sort_ratio(value: float) -> float:
    return 1e18 if value == math.inf else value


def _normalize_address(value: str) -> str:
    return str(value).lower()
