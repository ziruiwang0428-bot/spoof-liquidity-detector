from __future__ import annotations

from collections import defaultdict
from math import exp
from statistics import mean

from spoof_liquidity_detector.schema import AccountChainEvidence, AccountEconomics, AccountRiskProfile, DetectionResult


class AccountProfiler:
    def __init__(
        self,
        far_distance_bps: float = 150.0,
        near_touch_bps: float = 50.0,
        suspicious_profit_threshold: float = 0.0,
        suspicious_annualized_return: float = 0.20,
        suspicious_reward_to_fill_ratio: float = 0.05,
    ) -> None:
        self.far_distance_bps = far_distance_bps
        self.near_touch_bps = near_touch_bps
        self.suspicious_profit_threshold = suspicious_profit_threshold
        self.suspicious_annualized_return = suspicious_annualized_return
        self.suspicious_reward_to_fill_ratio = suspicious_reward_to_fill_ratio

    def profile(
        self,
        order_results: list[DetectionResult],
        economics: dict[str, AccountEconomics] | None = None,
        chain_evidence: dict[str, AccountChainEvidence] | None = None,
    ) -> list[AccountRiskProfile]:
        grouped: dict[str, list[DetectionResult]] = defaultdict(list)
        for result in order_results:
            grouped[result.maker].append(result)

        economics = economics or {}
        chain_evidence = chain_evidence or {}
        profiles = [
            self._profile_one(maker, rows, economics.get(maker), chain_evidence.get(maker))
            for maker, rows in grouped.items()
        ]
        return sorted(profiles, key=lambda item: item.account_risk_score, reverse=True)

    def _profile_one(
        self,
        maker: str,
        rows: list[DetectionResult],
        economics: AccountEconomics | None,
        chain_evidence: AccountChainEvidence | None,
    ) -> AccountRiskProfile:
        order_count = len(rows)
        cancelled = [row for row in rows if row.features.cancelled]
        filled = [row for row in rows if row.features.lifecycle.close_type == "fill"]
        near_touch_cancelled = [
            row
            for row in cancelled
            if row.features.approach_bps is not None and row.features.approach_bps <= self.near_touch_bps
        ]
        far_orders = [row for row in rows if row.features.distance_bps >= self.far_distance_bps]

        cancel_rate = _ratio(len(cancelled), order_count)
        fill_rate = _ratio(len(filled), order_count)
        near_touch_cancel_rate = _ratio(len(near_touch_cancelled), order_count)
        far_order_ratio = _ratio(len(far_orders), order_count)
        average_distance_bps = mean(row.features.distance_bps for row in rows)
        average_price_to_mid_ratio = mean(
            _price_to_mid_ratio(row.features.lifecycle.price, row.features.lifecycle.open_mid_price)
            for row in rows
        )
        total_notional = sum(row.features.notional for row in rows)
        average_order_risk = mean(row.risk_score for row in rows)

        subsidy = economics.subsidy if economics else 0.0
        cost = economics.cost if economics else 0.0
        net_profit = economics.net_profit if economics else 0.0
        annualized_return = economics.annualized_return if economics else 0.0
        chain_evidence_order_count = chain_evidence.confirmed_order_count if chain_evidence else 0
        chain_evidence_matched_log_count = chain_evidence.matched_log_count if chain_evidence else 0
        chain_evidence_ratio = chain_evidence.evidence_ratio if chain_evidence else 0.0
        chain_evidence_events = chain_evidence.event_names if chain_evidence else ()
        chain_fill_event_count = chain_evidence.fill_event_count if chain_evidence else 0
        chain_filled_notional = chain_evidence.filled_notional if chain_evidence else 0.0
        chain_evidence_observed = chain_evidence is not None
        reward_to_chain_fill_ratio = _reward_to_fill_ratio(
            subsidy,
            chain_filled_notional,
            chain_fill_event_count,
            chain_evidence_observed,
        )

        reasons = self._reasons(
            cancel_rate=cancel_rate,
            near_touch_cancel_rate=near_touch_cancel_rate,
            far_order_ratio=far_order_ratio,
            net_profit=net_profit,
            annualized_return=annualized_return,
            chain_evidence_order_count=chain_evidence_order_count,
            chain_evidence_matched_log_count=chain_evidence_matched_log_count,
            chain_evidence_events=chain_evidence_events,
            subsidy=subsidy,
            chain_fill_event_count=chain_fill_event_count,
            reward_to_chain_fill_ratio=reward_to_chain_fill_ratio,
            chain_evidence_observed=chain_evidence_observed,
        )
        account_risk_score = self._risk_score(
            near_touch_cancel_rate=near_touch_cancel_rate,
            far_order_ratio=far_order_ratio,
            average_order_risk=average_order_risk,
            net_profit=net_profit,
            annualized_return=annualized_return,
            chain_evidence_ratio=chain_evidence_ratio,
            chain_evidence_matched_log_count=chain_evidence_matched_log_count,
            subsidy=subsidy,
            chain_fill_event_count=chain_fill_event_count,
            reward_to_chain_fill_ratio=reward_to_chain_fill_ratio,
            chain_evidence_observed=chain_evidence_observed,
        )
        chain_locked = self._chain_locked(
            account_risk_score=account_risk_score,
            near_touch_cancel_rate=near_touch_cancel_rate,
            far_order_ratio=far_order_ratio,
            net_profit=net_profit,
            annualized_return=annualized_return,
            chain_evidence_matched_log_count=chain_evidence_matched_log_count,
            subsidy=subsidy,
            chain_fill_event_count=chain_fill_event_count,
            reward_to_chain_fill_ratio=reward_to_chain_fill_ratio,
            suspicious_reward_to_fill_ratio=self.suspicious_reward_to_fill_ratio,
            chain_evidence_observed=chain_evidence_observed,
        )
        if chain_locked and "chain_evidence_locked_account" not in reasons:
            reasons.append("chain_evidence_locked_account")

        return AccountRiskProfile(
            maker=maker,
            venue=_dominant_value(row.venue for row in rows),
            markets=tuple(sorted({row.market for row in rows})),
            order_count=order_count,
            cancel_rate=round(cancel_rate, 4),
            fill_rate=round(fill_rate, 4),
            near_touch_cancel_rate=round(near_touch_cancel_rate, 4),
            far_order_ratio=round(far_order_ratio, 4),
            average_distance_bps=round(average_distance_bps, 4),
            average_price_to_mid_ratio=round(average_price_to_mid_ratio, 6),
            total_notional=round(total_notional, 4),
            average_order_risk=round(average_order_risk, 4),
            subsidy=round(subsidy, 4),
            cost=round(cost, 4),
            net_profit=round(net_profit, 4),
            annualized_return=round(annualized_return, 4),
            account_risk_score=round(account_risk_score, 4),
            reasons=tuple(reasons),
            chain_evidence_order_count=chain_evidence_order_count,
            chain_evidence_matched_log_count=chain_evidence_matched_log_count,
            chain_evidence_ratio=round(chain_evidence_ratio, 4),
            chain_evidence_events=chain_evidence_events,
            chain_fill_event_count=chain_fill_event_count,
            chain_filled_notional=round(chain_filled_notional, 4),
            reward_to_chain_fill_ratio=round(reward_to_chain_fill_ratio, 6),
            chain_locked=chain_locked,
        )

    def _reasons(
        self,
        cancel_rate: float,
        near_touch_cancel_rate: float,
        far_order_ratio: float,
        net_profit: float,
        annualized_return: float,
        chain_evidence_order_count: int,
        chain_evidence_matched_log_count: int,
        chain_evidence_events: tuple[str, ...],
        subsidy: float,
        chain_fill_event_count: int,
        reward_to_chain_fill_ratio: float,
        chain_evidence_observed: bool,
    ) -> list[str]:
        reasons: list[str] = []
        if near_touch_cancel_rate >= 0.25:
            reasons.append("avoids_execution_near_touch")
        if far_order_ratio >= 0.50:
            reasons.append("posts_far_from_mid")
        if cancel_rate >= 0.60:
            reasons.append("high_cancel_rate")
        if net_profit > self.suspicious_profit_threshold:
            reasons.append("subsidy_positive_after_cost")
        if annualized_return >= self.suspicious_annualized_return:
            reasons.append("high_subsidy_annualized_return")
        if chain_evidence_order_count > 0:
            reasons.append("chain_order_event_confirmed")
        if chain_evidence_matched_log_count > 0:
            reasons.append("chain_order_log_matched")
        if "OrderCanceled" in chain_evidence_events:
            reasons.append("chain_cancel_event_confirmed")
        if "OrderFilledV2" in chain_evidence_events:
            reasons.append("chain_fill_event_confirmed")
        if chain_evidence_observed and subsidy > 0 and chain_fill_event_count == 0:
            reasons.append("reward_without_chain_fills")
        elif chain_evidence_observed and reward_to_chain_fill_ratio >= self.suspicious_reward_to_fill_ratio:
            reasons.append("high_reward_per_chain_fill")
        return reasons

    @staticmethod
    def _risk_score(
        near_touch_cancel_rate: float,
        far_order_ratio: float,
        average_order_risk: float,
        net_profit: float,
        annualized_return: float,
        chain_evidence_ratio: float,
        chain_evidence_matched_log_count: int,
        subsidy: float,
        chain_fill_event_count: int,
        reward_to_chain_fill_ratio: float,
        chain_evidence_observed: bool,
    ) -> float:
        reward_fill_penalty = 0.0
        if chain_evidence_observed and subsidy > 0 and chain_fill_event_count == 0:
            reward_fill_penalty = 0.9
        elif chain_evidence_observed and reward_to_chain_fill_ratio > 0:
            reward_fill_penalty = min(reward_to_chain_fill_ratio / 0.05, 1.0) * 0.6
        raw = (
            near_touch_cancel_rate * 2.2
            + far_order_ratio * 1.8
            + average_order_risk * 1.4
            + (0.8 if net_profit > 0 else 0.0)
            + min(max(annualized_return, 0.0), 1.0)
            + min(chain_evidence_ratio, 1.0) * 0.7
            + (0.5 if chain_evidence_matched_log_count > 0 else 0.0)
            + reward_fill_penalty
            - 2.0
        )
        return 1.0 / (1.0 + exp(-raw))

    @staticmethod
    def _chain_locked(
        account_risk_score: float,
        near_touch_cancel_rate: float,
        far_order_ratio: float,
        net_profit: float,
        annualized_return: float,
        chain_evidence_matched_log_count: int,
        subsidy: float,
        chain_fill_event_count: int,
        reward_to_chain_fill_ratio: float,
        suspicious_reward_to_fill_ratio: float,
        chain_evidence_observed: bool,
    ) -> bool:
        behavior_flagged = near_touch_cancel_rate >= 0.25 or far_order_ratio >= 0.50
        economics_flagged = net_profit > 0 or annualized_return >= 0.20
        reward_fill_flagged = (
            chain_evidence_observed and subsidy > 0 and chain_fill_event_count == 0
        ) or (
            chain_evidence_observed and reward_to_chain_fill_ratio >= suspicious_reward_to_fill_ratio
        )
        return (
            chain_evidence_matched_log_count > 0
            and account_risk_score >= 0.70
            and behavior_flagged
            and economics_flagged
            and reward_fill_flagged
        )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _price_to_mid_ratio(price: float, mid_price: float) -> float:
    if mid_price == 0:
        return 0.0
    return abs(price / mid_price - 1.0)


def _reward_to_fill_ratio(
    subsidy: float,
    chain_filled_notional: float,
    chain_fill_event_count: int,
    chain_evidence_observed: bool,
) -> float:
    if not chain_evidence_observed:
        return 0.0
    if subsidy <= 0:
        return 0.0
    if chain_filled_notional > 0:
        return subsidy / chain_filled_notional
    if chain_fill_event_count > 0:
        return subsidy / chain_fill_event_count
    return float("inf")


def _dominant_value(values) -> str:
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        counts[value] += 1
    return max(counts, key=counts.get)
