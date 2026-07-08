from __future__ import annotations

from spoof_liquidity_detector.providers.archive import HttpArchiveProvider

DEFAULT_POLYMARKET_ARCHIVE_URL = "https://archive.pmxt.dev/Polymarket/v2/"


class PolymarketProvider(HttpArchiveProvider):
    """Adapter for PMXT's Polymarket archive endpoint."""

    def __init__(self, base_url: str = DEFAULT_POLYMARKET_ARCHIVE_URL, timeout_seconds: float = 30.0) -> None:
        super().__init__(base_url=base_url, venue="polymarket", timeout_seconds=timeout_seconds)
