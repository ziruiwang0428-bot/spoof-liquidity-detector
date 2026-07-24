from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from spoof_liquidity_detector.providers.archive import HttpArchiveProvider
from spoof_liquidity_detector.providers.base import OrderEventProvider
from spoof_liquidity_detector.schema import OrderEvent

DEFAULT_POLYMARKET_ARCHIVE_URL = "https://archive.pmxt.dev/Polymarket/v2/"
DEFAULT_POLYMARKET_GAMMA_API_URL = "https://gamma-api.polymarket.com"
DEFAULT_POLYMARKET_CLOB_API_URL = "https://clob.polymarket.com"


class PolymarketProvider(HttpArchiveProvider):
    """Adapter for PMXT's Polymarket archive endpoint."""

    def __init__(self, base_url: str = DEFAULT_POLYMARKET_ARCHIVE_URL, timeout_seconds: float = 30.0) -> None:
        super().__init__(base_url=base_url, venue="polymarket", timeout_seconds=timeout_seconds)


class PolymarketLiveProvider(OrderEventProvider):
    """Client for Polymarket's public Gamma and CLOB endpoints."""

    def __init__(
        self,
        gamma_base_url: str = DEFAULT_POLYMARKET_GAMMA_API_URL,
        clob_base_url: str = DEFAULT_POLYMARKET_CLOB_API_URL,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.gamma_base_url = gamma_base_url.rstrip("/")
        self.clob_base_url = clob_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def list_markets(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        active: bool = True,
        closed: bool = False,
    ) -> list[dict[str, Any]]:
        payload = self._get_gamma(
            "/markets",
            {
                "limit": limit,
                "offset": offset,
                "active": str(active).lower(),
                "closed": str(closed).lower(),
            },
        )
        if isinstance(payload, list):
            return payload
        return list(payload.get("markets") or payload.get("data") or [])

    def fetch_order_book(self, *, token_id: str) -> dict[str, Any]:
        return self._get_clob("/book", {"token_id": token_id})

    def load_events(self) -> list[OrderEvent]:
        raise NotImplementedError(
            "Polymarket public CLOB book data is aggregated and does not include maker-level open/cancel/fill events. "
            "Use archive conversion or authenticated/vendor order feeds for account-level spoof detection."
        )

    def _get_gamma(self, path: str, query: dict[str, Any] | None = None) -> Any:
        return self._get(self.gamma_base_url, path, query)

    def _get_clob(self, path: str, query: dict[str, Any] | None = None) -> Any:
        return self._get(self.clob_base_url, path, query)

    def _get(self, base_url: str, path: str, query: dict[str, Any] | None = None) -> Any:
        url = f"{base_url}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query)}"

        request = Request(
            url,
            headers={
                "accept": "application/json",
                "user-agent": "Mozilla/5.0 spoof-liquidity-detector/0.1",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)
