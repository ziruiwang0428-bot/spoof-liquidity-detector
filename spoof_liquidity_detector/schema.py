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


@dataclass(frozen=True)
class AccountEconomics:
    maker: str
    subsidy: float
    cost: float
    capital: float
    period_days: float

    @property
    def net_profit(self) -> float:
        return self.subsidy - self.cost

    @property
    def annualized_return(self) -> float:
        if self.capital <= 0 or self.period_days <= 0:
            return 0.0
        return self.net_profit / self.capital * 365.0 / self.period_days


@dataclass(frozen=True)
class AccountRiskProfile:
    maker: str
    venue: str
    markets: tuple[str, ...]
    order_count: int
    cancel_rate: float
    fill_rate: float
    near_touch_cancel_rate: float
    far_order_ratio: float
    average_distance_bps: float
    average_price_to_mid_ratio: float
    total_notional: float
    average_order_risk: float
    subsidy: float
    cost: float
    net_profit: float
    annualized_return: float
    account_risk_score: float
    reasons: tuple[str, ...]
    chain_evidence_order_count: int = 0
    chain_evidence_matched_log_count: int = 0
    chain_evidence_ratio: float = 0.0
    chain_evidence_events: tuple[str, ...] = ()
    chain_fill_event_count: int = 0
    chain_filled_notional: float = 0.0
    reward_to_chain_fill_ratio: float = 0.0
    chain_locked: bool = False


@dataclass(frozen=True)
class ChainEventEvidence:
    event_name: str
    order_hash: str
    maker: str
    contract: str
    block_number: int | None
    transaction_hash: str
    log_index: int | None
    order_type: int | None = None
    yt: str = ""
    token: str = ""
    taker: str = ""
    notional_volume: int | None = None
    fee_paid: int | None = None


@dataclass(frozen=True)
class ChainEvidence:
    venue: str
    chain_id: int
    order_id: str
    maker: str
    transaction_hashes: tuple[str, ...]
    confirmed_transaction_count: int
    matched_log_count: int
    blocks: tuple[int, ...]
    contracts: tuple[str, ...]
    status: str
    events: tuple[ChainEventEvidence, ...] = ()

    @property
    def confirmed(self) -> bool:
        return self.confirmed_transaction_count > 0 or self.matched_log_count > 0

    @property
    def order_linked(self) -> bool:
        return self.matched_log_count > 0


@dataclass(frozen=True)
class AccountChainEvidence:
    maker: str
    order_count: int
    confirmed_order_count: int
    matched_log_count: int
    fill_event_count: int
    filled_notional: float
    blocks: tuple[int, ...]
    contracts: tuple[str, ...]
    event_counts: dict[str, int] | None = None

    @property
    def evidence_ratio(self) -> float:
        if self.order_count == 0:
            return 0.0
        return self.confirmed_order_count / self.order_count

    @property
    def event_names(self) -> tuple[str, ...]:
        if not self.event_counts:
            return ()
        return tuple(sorted(name for name, count in self.event_counts.items() if count > 0))


@dataclass(frozen=True)
class ChainFillSummary:
    venue: str
    chain_id: int
    maker: str
    fill_count: int
    filled_notional: float
    fee_paid: float
    reward: float = 0.0
    reward_to_fill_ratio: float = 0.0
    blocks: tuple[int, ...] = ()
    contracts: tuple[str, ...] = ()
    transaction_hashes: tuple[str, ...] = ()
    risk_score: float = 0.0
    risk_level: str = "unscored"
    evidence_mode: str = "chain_fill"
    reasons: tuple[str, ...] = ()
