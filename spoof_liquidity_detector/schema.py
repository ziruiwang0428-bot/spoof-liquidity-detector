from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Side = Literal["buy", "sell"]
EventType = Literal["open", "cancel", "fill"]


@dataclass(frozen=True)
class OrderEvent:
    venue: str
    market: str
    order_id: str
    maker: str
    side: Side
    price: float
    quantity: float
    event_type: EventType
    timestamp: datetime
    mid_price: float
    best_bid: float
    best_ask: float


@dataclass(frozen=True)
class OrderLifecycle:
    venue: str
    market: str
    order_id: str
    maker: str
    side: Side
    price: float
    quantity: float
    opened_at: datetime
    closed_at: datetime | None
    close_type: EventType | None
    open_mid_price: float
    close_mid_price: float | None
    close_best_bid: float | None
    close_best_ask: float | None

    @property
    def lifetime_seconds(self) -> float:
        if self.closed_at is None:
            return float("inf")
        return max((self.closed_at - self.opened_at).total_seconds(), 0.0)

    @property
    def notional(self) -> float:
        return self.price * self.quantity

    @property
    def cancelled(self) -> bool:
        return self.close_type == "cancel"


@dataclass(frozen=True)
class OrderFeatures:
    lifecycle: OrderLifecycle
    distance_bps: float
    approach_bps: float | None
    lifetime_seconds: float
    notional: float
    cancelled: bool


@dataclass(frozen=True)
class DetectionResult:
    order_id: str
    maker: str
    venue: str
    market: str
    risk_score: float
    p_value: float
    z_score: float
    reasons: tuple[str, ...]
    features: OrderFeatures
