from __future__ import annotations

from spoof_liquidity_detector.schema import OrderEvent, OrderLifecycle


def build_lifecycles(events: list[OrderEvent]) -> list[OrderLifecycle]:
    opened: dict[str, OrderEvent] = {}
    lifecycles: list[OrderLifecycle] = []

    for event in sorted(events, key=lambda item: item.timestamp):
        if event.event_type == "open":
            opened[event.order_id] = event
            continue

        start = opened.pop(event.order_id, None)
        if start is None:
            continue

        lifecycles.append(
            OrderLifecycle(
                venue=start.venue,
                market=start.market,
                order_id=start.order_id,
                maker=start.maker,
                side=start.side,
                price=start.price,
                quantity=start.quantity,
                opened_at=start.timestamp,
                closed_at=event.timestamp,
                close_type=event.event_type,
                open_mid_price=start.mid_price,
                close_mid_price=event.mid_price,
                close_best_bid=event.best_bid,
                close_best_ask=event.best_ask,
            )
        )

    for start in opened.values():
        lifecycles.append(
            OrderLifecycle(
                venue=start.venue,
                market=start.market,
                order_id=start.order_id,
                maker=start.maker,
                side=start.side,
                price=start.price,
                quantity=start.quantity,
                opened_at=start.timestamp,
                closed_at=None,
                close_type=None,
                open_mid_price=start.mid_price,
                close_mid_price=None,
                close_best_bid=None,
                close_best_ask=None,
            )
        )

    return lifecycles
