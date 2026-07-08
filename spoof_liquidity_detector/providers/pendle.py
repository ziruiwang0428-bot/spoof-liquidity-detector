from __future__ import annotations

from spoof_liquidity_detector.providers.base import OrderEventProvider
from spoof_liquidity_detector.schema import OrderEvent

DEFAULT_PENDLE_LIMIT_ORDER_URL = "https://app.pendle.finance/limit-order"


class PendleProvider(OrderEventProvider):
    """Placeholder adapter for Pendle limit-order data."""

    def __init__(self, source_url: str = DEFAULT_PENDLE_LIMIT_ORDER_URL, api_key: str | None = None) -> None:
        self.source_url = source_url
        self.api_key = api_key

    def load_events(self) -> list[OrderEvent]:
        raise NotImplementedError(
            "Pendle's public limit-order app URL is not a normalized order-event API. "
            "Connect a Pendle API or vendor feed here and return open/cancel/fill OrderEvent objects."
        )
