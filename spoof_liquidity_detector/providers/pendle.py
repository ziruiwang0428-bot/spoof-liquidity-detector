from __future__ import annotations

from spoof_liquidity_detector.providers.base import OrderEventProvider
from spoof_liquidity_detector.schema import OrderEvent


class PendleProvider(OrderEventProvider):
    """Placeholder adapter for a Pendle or third-party data vendor feed."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    def load_events(self) -> list[OrderEvent]:
        raise NotImplementedError(
            "Wire the vendor's Pendle order-event endpoint here and return normalized OrderEvent objects."
        )
