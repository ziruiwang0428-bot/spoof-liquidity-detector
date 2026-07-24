from __future__ import annotations

import json
from datetime import datetime, timezone
from statistics import median
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
        chain_id: int | None = None,
        order_limit: int = 100,
    ) -> None:
        self.source_url = source_url
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.chain_id = chain_id
        self.order_limit = order_limit

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
        active_payload = self.fetch_limit_orders(chain_id=self.chain_id, limit=self.order_limit, is_active=True)
        inactive_payload = self.fetch_limit_orders(chain_id=self.chain_id, limit=self.order_limit, is_active=False)
        orders = list(active_payload.get("results", [])) + list(inactive_payload.get("results", []))
        market_references = _build_market_references(orders)

        events: list[OrderEvent] = []
        for order in orders:
            open_event = _order_to_event(order, "open", market_references)
            if open_event is None:
                continue
            events.append(open_event)

            close_type = _close_type(order)
            if close_type is not None:
                close_event = _order_to_event(order, close_type, market_references)
                if close_event is not None and close_event.timestamp >= open_event.timestamp:
                    events.append(close_event)

        return events

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


def _order_to_event(
    order: dict[str, Any],
    event_type: str,
    market_references: dict[str, tuple[float, float, float]],
) -> OrderEvent | None:
    order_id = str(order.get("id") or "")
    maker = str(order.get("maker") or "")
    if not order_id or not maker:
        return None

    market = _market_id(order)
    price = _implied_rate_price(order)
    if price <= 0:
        return None

    mid_price, best_bid, best_ask = market_references.get(market, (price, price, price))
    return OrderEvent(
        venue="pendle",
        market=market,
        order_id=order_id,
        maker=maker,
        side=_side(order),
        price=price,
        quantity=_quantity(order, price),
        event_type=event_type,  # type: ignore[arg-type]
        timestamp=_event_timestamp(order, event_type),
        mid_price=mid_price,
        best_bid=best_bid,
        best_ask=best_ask,
    )


def _build_market_references(orders: list[dict[str, Any]]) -> dict[str, tuple[float, float, float]]:
    grouped: dict[str, list[float]] = {}
    for order in orders:
        price = _implied_rate_price(order)
        if price <= 0:
            continue
        grouped.setdefault(_market_id(order), []).append(price)

    references: dict[str, tuple[float, float, float]] = {}
    for market, prices in grouped.items():
        mid = median(prices)
        bids = [price for price in prices if price <= mid]
        asks = [price for price in prices if price >= mid]
        best_bid = max(bids) if bids else mid
        best_ask = min(asks) if asks else mid
        references[market] = (mid, best_bid, best_ask)
    return references


def _close_type(order: dict[str, Any]) -> str | None:
    if bool(order.get("isActive")):
        return None
    status = str(order.get("status") or "").upper()
    filled_status = order.get("orderFilledStatus") or {}
    filled_notional = _float_or_zero(filled_status.get("notionalVolume"))
    if bool(order.get("isCanceled")) or "CANCEL" in status:
        return "cancel"
    if filled_notional > 0 or "FILL" in status or "FILLED" in status:
        return "fill"
    return "cancel"


def _market_id(order: dict[str, Any]) -> str:
    return str(order.get("yt") or order.get("token") or order.get("chainId") or "unknown")


def _implied_rate_price(order: dict[str, Any]) -> float:
    value = _float_or_zero(order.get("lnImpliedRate"))
    if value > 1_000:
        return value / 1e18
    if value > 0:
        return value
    order_state = order.get("orderState") or {}
    return _float_or_zero(order_state.get("psRate") or order_state.get("ysRate"))


def _quantity(order: dict[str, Any], price: float) -> float:
    order_state = order.get("orderState") or {}
    notional_usd = _float_or_zero(order_state.get("notionalVolumeUSD"))
    if notional_usd > 0 and price > 0:
        return notional_usd / price
    making_amount = _float_or_zero(order.get("currentMakingAmount") or order.get("makingAmount"))
    if making_amount > 1e12:
        return making_amount / 1e18
    return max(making_amount, 1.0)


def _side(order: dict[str, Any]) -> str:
    order_state = order.get("orderState") or {}
    order_type = str(order_state.get("orderType") or order.get("type") or "").upper()
    return "sell" if "SHORT" in order_type else "buy"


def _event_timestamp(order: dict[str, Any], event_type: str) -> datetime:
    if event_type == "open":
        return _parse_timestamp(order.get("createdAt") or order.get("latestEventTimestamp"))
    return _parse_timestamp(order.get("latestEventTimestamp") or order.get("createdAt"))


def _parse_timestamp(value: object) -> datetime:
    if value in (None, ""):
        return datetime.now(timezone.utc)
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _float_or_zero(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
