from __future__ import annotations

from spoof_liquidity_detector.schema import OrderFeatures, OrderLifecycle


def build_features(lifecycles: list[OrderLifecycle]) -> list[OrderFeatures]:
    return [_build_one(item) for item in lifecycles]


def _build_one(lifecycle: OrderLifecycle) -> OrderFeatures:
    distance_bps = _bps_distance(lifecycle.price, lifecycle.open_mid_price)
    approach_bps = None

    if lifecycle.cancelled and lifecycle.close_mid_price is not None:
        touch_price = lifecycle.close_best_bid if lifecycle.side == "sell" else lifecycle.close_best_ask
        reference = touch_price or lifecycle.close_mid_price
        approach_bps = _bps_distance(lifecycle.price, reference)

    return OrderFeatures(
        lifecycle=lifecycle,
        distance_bps=distance_bps,
        approach_bps=approach_bps,
        lifetime_seconds=lifecycle.lifetime_seconds,
        notional=lifecycle.notional,
        cancelled=lifecycle.cancelled,
    )


def _bps_distance(left: float, right: float) -> float:
    if right == 0:
        return 0.0
    return abs(left - right) / abs(right) * 10_000
