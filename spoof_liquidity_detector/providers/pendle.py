from __future__ import annotations

from spoof_liquidity_detector.providers.archive import HttpArchiveProvider

DEFAULT_PENDLE_ARCHIVE_URL = "https://archive.pmxt.dev/Polymarket/v2/"


class PendleProvider(HttpArchiveProvider):
    """Adapter for the user-provided Pendle/PMXT archive endpoint."""

    def __init__(self, base_url: str = DEFAULT_PENDLE_ARCHIVE_URL, timeout_seconds: float = 30.0) -> None:
        super().__init__(base_url=base_url, venue="pendle", timeout_seconds=timeout_seconds)
