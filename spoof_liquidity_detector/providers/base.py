from __future__ import annotations

from abc import ABC, abstractmethod

from spoof_liquidity_detector.schema import OrderEvent


class OrderEventProvider(ABC):
    """Interface implemented by all market data adapters."""

    @abstractmethod
    def load_events(self) -> list[OrderEvent]:
        """Return normalized order events sorted by timestamp."""
