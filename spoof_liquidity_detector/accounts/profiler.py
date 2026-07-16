from __future__ import annotations

from collections import defaultdict
from math import exp
from statistics import mean

from spoof_liquidity_detector.schema import AccountEconomics, AccountRiskProfile, DetectionResult


class AccountProfiler:
    def __init__(
        self,
        far_distance_bps: float = 150.0,
        near_touch_bps: float = 50.0,
        suspicious_profit_threshold: float = 0.0,
        suspicious_annualized_return: float = 0.20,
    ) -> None:
        self.far_distance_bps = far_distance_bps
        self.near_touch_bps = near_touch_bps
        self.suspicious_profit_threshold = suspicious_profit_threshold
        self.suspicious_annualized_return = suspicious_annualized_return

    def profile(
        self,
        order_results: list[DetectionResult],
        economics: dict[str, AccountEconomics] | None = None,
    ) -> list[AccountRiskProfile]:
        grouped: dict[str, list[DetectionResult]] = defaultdict(list)
        for result in order_results:
            grouped[result.maker].append(result)

        economics = economics or {}
        profiles = [
            self._profile_one(maker, rows, economics.get(maker))
            for maker, rows in grouped.items()
        ]
        return sorted(profiles, key=lambda item: item.account_risk_score, reverse=True)

    def _profile_one(
        self,
        maker: str,
        rows: list[DetectionResult],
        economics: AccountEconomics | None,
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

        reasons = self._reasons(
            cancel_rate=cancel_rate,
            near_touch_cancel_rate=near_touch_cancel_rate,
            far_order_ratio=far_order_ratio,
            net_profit=net_profit,
            annualized_return=annualized_return,
        )
        account_risk_score = self._risk_score(
            near_touch_cancel_rate=near_touch_cancel_rate,
            far_order_ratio=far_order_ratio,
            average_order_risk=average_order_risk,
            net_profit=net_profit,
            annualized_return=annualized_return,
        )

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
        )

    def _reasons(
        self,
        cancel_rate: float,
        near_touch_cancel_rate: float,
        far_order_ratio: float,
        net_profit: float,
        annualized_return: float,
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
        return reasons

    @staticmethod
    def _risk_score(
        near_touch_cancel_rate: float,
        far_order_ratio: float,
        average_order_risk: float,
        net_profit: float,
        annualized_return: float,
    ) -> float:
        raw = (
            near_touch_cancel_rate * 2.2
            + far_order_ratio * 1.8
            + average_order_risk * 1.4
            + (0.8 if net_profit > 0 else 0.0)
            + min(max(annualized_return, 0.0), 1.0)
            - 2.0
        )
        return 1.0 / (1.0 + exp(-raw))


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _price_to_mid_ratio(price: float, mid_price: float) -> float:
    if mid_price == 0:
        return 0.0
    return abs(price / mid_price - 1.0)


def _dominant_value(values) -> str:
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        counts[value] += 1
    return max(counts, key=counts.get)
