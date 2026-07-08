from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from spoof_liquidity_detector.providers.base import OrderEventProvider
from spoof_liquidity_detector.schema import EventType, OrderEvent, Side


class CsvOrderEventProvider(OrderEventProvider):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load_events(self) -> list[OrderEvent]:
        events: list[OrderEvent] = []
        with self.path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                events.append(
                    OrderEvent(
                        venue=row["venue"],
                        market=row["market"],
                        order_id=row["order_id"],
                        maker=row["maker"],
                        side=self._side(row["side"]),
                        price=float(row["price"]),
                        quantity=float(row["quantity"]),
                        event_type=self._event_type(row["event_type"]),
                        timestamp=datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
                        mid_price=float(row["mid_price"]),
                        best_bid=float(row["best_bid"]),
                        best_ask=float(row["best_ask"]),
                    )
                )
        return sorted(events, key=lambda event: event.timestamp)

    @staticmethod
    def _side(value: str) -> Side:
        if value not in {"buy", "sell"}:
            raise ValueError(f"Unsupported side: {value}")
        return value  # type: ignore[return-value]

    @staticmethod
    def _event_type(value: str) -> EventType:
        if value not in {"open", "cancel", "fill"}:
            raise ValueError(f"Unsupported event type: {value}")
        return value  # type: ignore[return-value]
