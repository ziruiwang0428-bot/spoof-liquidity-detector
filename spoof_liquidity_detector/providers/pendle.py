from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from spoof_liquidity_detector.providers.base import OrderEventProvider
from spoof_liquidity_detector.schema import OrderEvent

DEFAULT_PENDLE_LIMIT_ORDER_URL = "https://app.pendle.finance/limit-order"
DEFAULT_PENDLE_API_BASE_URL = "https://api-v2.pendle.finance/bff"
DEFAULT_PENDLE_SDK_UI_VERSION = "1.0.0"


class PendleProvider(OrderEventProvider):
    """Client for Pendle's public limit-order backend endpoints."""

    def __init__(
        self,
        source_url: str = DEFAULT_PENDLE_LIMIT_ORDER_URL,
        api_base_url: str = DEFAULT_PENDLE_API_BASE_URL,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.source_url = source_url
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def list_incentive_configs(self) -> list[dict[str, Any]]:
        payload = self._get("/v1/limit-orders/incentive/configs")
        return list(payload.get("configs", []))

    def fetch_limit_orders(
        self,
        *,
        chain_id: int | None = None,
        limit: int = 100,
        skip: int = 0,
        is_active: bool | None = True,
        maker: str | None = None,
        yt: str | None = None,
        order_by: str = "latestEventTimestamp:-1",
    ) -> dict[str, Any]:
        query: dict[str, Any] = {
            "limit": limit,
            "skip": skip,
            "order_by": order_by,
        }
        if chain_id is not None:
            query["chainId"] = chain_id
        if is_active is not None:
            query["isActive"] = str(is_active).lower()
        if maker:
            query["maker"] = maker
        if yt:
            query["yt"] = yt
        return self._get("/v1/limit-orders", query)

    def fetch_order_book(
        self,
        *,
        chain_id: int,
        market: str,
        limit: int = 10,
        precision_decimal: int = 3,
    ) -> dict[str, Any]:
        if precision_decimal > 3:
            raise ValueError("Pendle order-book precisionDecimal must be 3 or lower.")
        return self._get(
            f"/v1/limit-orders/book/{chain_id}",
            {
                "market": market,
                "limit": limit,
                "precisionDecimal": precision_decimal,
            },
        )

    def load_events(self) -> list[OrderEvent]:
        raise NotImplementedError(
            "Pendle's public backend is connected for raw limit-order exploration. "
            "Detection still requires converting implied-APY orders into normalized open/cancel/fill OrderEvent objects."
        )

    def _get(self, path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.api_base_url}/{path.lstrip('/')}"
        if query:
            clean_query = {key: value for key, value in query.items() if value is not None}
            url = f"{url}?{urlencode(clean_query)}"

        request = Request(
            url,
            headers={
                "accept": "application/json",
                "origin": "https://app.pendle.finance",
                "referer": self.source_url,
                "user-agent": "Mozilla/5.0 spoof-liquidity-detector/0.1",
                "x-sdk-ui-version": DEFAULT_PENDLE_SDK_UI_VERSION,
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)
