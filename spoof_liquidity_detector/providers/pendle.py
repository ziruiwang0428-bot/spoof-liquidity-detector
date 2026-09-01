from __future__ import annotations

import json
import ssl
from datetime import datetime, timedelta, timezone
from statistics import median
from time import sleep
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from spoof_liquidity_detector.providers.base import OrderEventProvider
from spoof_liquidity_detector.schema import AccountEconomics, OrderEvent

DEFAULT_PENDLE_LIMIT_ORDER_URL = "https://app.pendle.finance/limit-order"
DEFAULT_PENDLE_API_BASE_URL = "https://api-v2.pendle.finance/bff"
DEFAULT_PENDLE_CORE_API_BASE_URL = "https://api-v2.pendle.finance/core"
DEFAULT_PENDLE_SDK_UI_VERSION = "1.0.0"
MAX_PENDLE_SKIP = 1000


class PendleProvider(OrderEventProvider):
    """Client for Pendle's public limit-order backend endpoints."""

    def __init__(
        self,
        source_url: str = DEFAULT_PENDLE_LIMIT_ORDER_URL,
        api_base_url: str = DEFAULT_PENDLE_API_BASE_URL,
        core_api_base_url: str = DEFAULT_PENDLE_CORE_API_BASE_URL,
        timeout_seconds: float = 30.0,
        chain_id: int | None = None,
        order_limit: int = 100,
        lookback_days: float | None = None,
        page_size: int = 100,
        max_pages: int = 25,
        retry_attempts: int = 3,
    ) -> None:
        self.source_url = source_url
        self.api_base_url = api_base_url.rstrip("/")
        self.core_api_base_url = core_api_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.chain_id = chain_id
        self.order_limit = order_limit
        self.lookback_days = lookback_days
        self.page_size = page_size
        self.max_pages = max_pages
        self.retry_attempts = retry_attempts

    def list_incentive_configs(self) -> list[dict[str, Any]]:
        payload = self._get("/v1/limit-orders/incentive/configs")
        return list(payload.get("configs", []))

    def fetch_user_incentive_aggregate(self, *, user: str) -> dict[str, Any]:
        query: dict[str, Any] = {"user": user}
        if self.chain_id is not None:
            query["chainId"] = self.chain_id
        return self._get("/v1/limit-orders/incentive/user/aggregate", query)

    def fetch_user_reward_history(self, *, user: str) -> dict[str, Any]:
        query: dict[str, Any] = {"user": user}
        if self.chain_id is not None:
            query["chainId"] = self.chain_id
        return self._get("/v1/limit-orders/incentive/user/reward-history", query)

    def fetch_account_economics(self, makers: list[str]) -> dict[str, AccountEconomics]:
        economics: dict[str, AccountEconomics] = {}
        for maker in makers:
            history = self.fetch_user_reward_history(user=maker)
            aggregate = self.fetch_user_incentive_aggregate(user=maker)
            economics[maker] = _reward_payload_to_economics(
                maker=maker,
                history=history,
                aggregate=aggregate,
                chain_id=self.chain_id,
                lookback_days=self.lookback_days,
            )
        return economics

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
        return self.events_from_orders(self.fetch_detection_orders())

    def events_from_orders(self, orders: list[dict[str, Any]]) -> list[OrderEvent]:
        """Normalize an already-fetched order batch for repeatable API and chain auditing."""
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

    def fetch_detection_orders(self) -> list[dict[str, Any]]:
        if self.lookback_days is not None:
            return self.fetch_historical_limit_orders()

        orders: list[dict[str, Any]] = []
        for is_active in (True, False):
            orders.extend(self._fetch_paginated_limit_orders(is_active=is_active, cutoff=None))
        return orders

    def fetch_historical_limit_orders(self) -> list[dict[str, Any]]:
        if self.chain_id is None:
            raise ValueError("chain_id is required for Pendle historical scans.")

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.lookback_days or 1.0)
        orders: list[dict[str, Any]] = []
        for archived in (False, True):
            orders.extend(
                self._fetch_core_limit_orders(
                    archived=archived,
                    timestamp_start=start,
                    timestamp_end=end,
                )
            )
        return _dedupe_orders(orders)[: self.order_limit]

    def _fetch_core_limit_orders(
        self,
        *,
        archived: bool,
        timestamp_start: datetime,
        timestamp_end: datetime,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        resume_token = None
        page_count = 0
        path = "/v2/limit-orders/archived" if archived else "/v2/limit-orders"

        while len(rows) < self.order_limit and page_count < self.max_pages:
            query: dict[str, Any] = {
                "chainId": self.chain_id,
                "limit": min(self.page_size, self.order_limit - len(rows)),
                "timestamp_start": _format_api_timestamp(timestamp_start),
                "timestamp_end": _format_api_timestamp(timestamp_end),
            }
            if resume_token:
                query["resumeToken"] = resume_token

            payload = self._get(path, query, base_url=self.core_api_base_url)
            page = list(payload.get("results", []))
            if not page:
                break

            rows.extend(page)
            resume_token = payload.get("resumeToken")
            if not resume_token:
                break
            page_count += 1

        return rows[: self.order_limit]

    def _fetch_paginated_limit_orders(
        self,
        *,
        is_active: bool,
        cutoff: datetime | None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        skip = 0
        page_count = 0

        while len(rows) < self.order_limit and page_count < self.max_pages and skip <= MAX_PENDLE_SKIP:
            page_limit = min(self.page_size, self.order_limit - len(rows))
            payload = self.fetch_limit_orders(
                chain_id=self.chain_id,
                limit=page_limit,
                skip=skip,
                is_active=is_active,
            )
            page = list(payload.get("results", []))
            if not page:
                break

            if cutoff is None:
                rows.extend(page)
            else:
                rows.extend(order for order in page if _order_timestamp(order) >= cutoff)
                if all(_order_timestamp(order) < cutoff for order in page):
                    break

            skip += len(page)
            page_count += 1

        return rows[: self.order_limit]

    def _get(
        self,
        path: str,
        query: dict[str, Any] | None = None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        url = f"{(base_url or self.api_base_url).rstrip('/')}/{path.lstrip('/')}"
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
        last_error: Exception | None = None
        for attempt in range(self.retry_attempts):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    body = response.read().decode("utf-8")
                return json.loads(body)
            except HTTPError as error:
                if error.code not in {408, 429, 500, 502, 503, 504}:
                    raise
                last_error = error
            except (TimeoutError, URLError, ssl.SSLError) as error:
                last_error = error

            if attempt < self.retry_attempts - 1:
                sleep(0.7 * (attempt + 1))

        if last_error is not None:
            raise last_error
        raise RuntimeError("Pendle request failed without an exception.")


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


def _order_timestamp(order: dict[str, Any]) -> datetime:
    return _parse_timestamp(order.get("latestEventTimestamp") or order.get("createdAt"))


def _format_api_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _dedupe_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for order in sorted(orders, key=_order_timestamp, reverse=True):
        order_id = str(order.get("id") or "")
        if not order_id or order_id in seen:
            continue
        seen.add(order_id)
        deduped.append(order)
    return deduped


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


def _reward_payload_to_economics(
    *,
    maker: str,
    history: dict[str, Any],
    aggregate: dict[str, Any],
    chain_id: int | None,
    lookback_days: float | None,
) -> AccountEconomics:
    cutoff = None
    if lookback_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    subsidy = 0.0
    capital_samples: list[float] = []
    start_dates: list[datetime] = []
    end_dates: list[datetime] = []

    for epoch in history.get("epochs", []):
        start = _parse_timestamp(epoch.get("startEpochDate"))
        end = _parse_timestamp(epoch.get("endEpochDate"))
        if cutoff is not None and end < cutoff:
            continue

        epoch_reward = 0.0
        epoch_capital = 0.0
        for market in epoch.get("markets", []):
            if chain_id is not None and int(market.get("chainId", 0)) != chain_id:
                continue
            epoch_reward += _float_or_zero(market.get("myReward"))
            epoch_capital += _float_or_zero(market.get("averageMakingOrderValueUsd"))

        if epoch_reward > 0 or epoch_capital > 0:
            subsidy += epoch_reward
            capital_samples.append(epoch_capital)
            start_dates.append(start)
            end_dates.append(end)

    if capital_samples:
        capital = sum(capital_samples) / len(capital_samples)
    else:
        capital = _float_or_zero(aggregate.get("userMakingAmountUsdIncentivized"))

    if start_dates and end_dates:
        period_days = max((max(end_dates) - min(start_dates)).total_seconds() / 86_400, 1.0)
    else:
        period_days = max(lookback_days or 7.0, 1.0)

    if subsidy == 0.0:
        subsidy = _float_or_zero(aggregate.get("currentEpochReward"))

    return AccountEconomics(
        maker=maker,
        subsidy=subsidy,
        cost=0.0,
        capital=capital,
        period_days=period_days,
    )
