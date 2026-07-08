from __future__ import annotations

from collections import defaultdict
from math import exp, sqrt
from statistics import mean, pstdev

from spoof_liquidity_detector.schema import DetectionResult, OrderFeatures


class SuspiciousLiquidityDetector:
    def __init__(
        self,
        far_distance_bps: float = 150.0,
        near_touch_bps: float = 50.0,
        short_lifetime_seconds: float = 180.0,
        min_notional: float = 1_000.0,
    ) -> None:
        self.far_distance_bps = far_distance_bps
        self.near_touch_bps = near_touch_bps
        self.short_lifetime_seconds = short_lifetime_seconds
        self.min_notional = min_notional

    def score(self, features: list[OrderFeatures]) -> list[DetectionResult]:
        grouped = self._group_by_market(features)
        results: list[DetectionResult] = []

        for feature in features:
            peer_scores = [self._raw_suspicion(item) for item in grouped[feature.lifecycle.market]]
            raw_score = self._raw_suspicion(feature)
            z_score = self._z_score(raw_score, peer_scores)
            p_value = self._empirical_p_value(raw_score, peer_scores)
            risk_score = self._sigmoid(raw_score + max(z_score, 0.0) * 0.35 - 2.0)

            results.append(
                DetectionResult(
                    order_id=feature.lifecycle.order_id,
                    maker=feature.lifecycle.maker,
                    venue=feature.lifecycle.venue,
                    market=feature.lifecycle.market,
                    risk_score=round(risk_score, 4),
                    p_value=round(p_value, 4),
                    z_score=round(z_score, 4),
                    reasons=tuple(self._reasons(feature)),
                    features=feature,
                )
            )

        return sorted(results, key=lambda item: item.risk_score, reverse=True)

    def _raw_suspicion(self, feature: OrderFeatures) -> float:
        score = 0.0
        if feature.cancelled:
            score += 1.0
        if feature.distance_bps >= self.far_distance_bps:
            score += min(feature.distance_bps / self.far_distance_bps, 3.0)
        if feature.lifetime_seconds <= self.short_lifetime_seconds:
            score += 1.3
        if feature.approach_bps is not None and feature.approach_bps <= self.near_touch_bps:
            score += 1.4
        if feature.notional >= self.min_notional:
            score += min(feature.notional / self.min_notional, 2.0) * 0.4
        return score

    def _reasons(self, feature: OrderFeatures) -> list[str]:
        reasons: list[str] = []
        if feature.cancelled:
            reasons.append("cancelled")
        if feature.distance_bps >= self.far_distance_bps:
            reasons.append("far_from_mid_at_open")
        if feature.lifetime_seconds <= self.short_lifetime_seconds:
            reasons.append("short_lifetime")
        if feature.approach_bps is not None and feature.approach_bps <= self.near_touch_bps:
            reasons.append("cancelled_near_touch")
        if feature.notional >= self.min_notional:
            reasons.append("large_notional")
        return reasons

    @staticmethod
    def _group_by_market(features: list[OrderFeatures]) -> dict[str, list[OrderFeatures]]:
        grouped: dict[str, list[OrderFeatures]] = defaultdict(list)
        for feature in features:
            grouped[feature.lifecycle.market].append(feature)
        return grouped

    @staticmethod
    def _z_score(value: float, population: list[float]) -> float:
        if len(population) < 2:
            return 0.0
        sigma = pstdev(population)
        if sigma == 0:
            return 0.0
        return (value - mean(population)) / sigma

    @staticmethod
    def _empirical_p_value(value: float, population: list[float]) -> float:
        if not population:
            return 1.0
        more_extreme = sum(1 for item in population if item >= value)
        return (more_extreme + 1) / (len(population) + 1)

    @staticmethod
    def _sigmoid(value: float) -> float:
        return 1.0 / (1.0 + exp(-value))
