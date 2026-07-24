from __future__ import annotations

import argparse
import json
from pathlib import Path

from spoof_liquidity_detector.accounts import load_account_economics
from spoof_liquidity_detector.pipeline import DetectionPipeline
from spoof_liquidity_detector.providers import (
    ArchiveSnapshot,
    CsvOrderEventProvider,
    PendleProvider,
    PolymarketLiveProvider,
    PolymarketProvider,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect suspicious fleeting liquidity from order events.")
    parser.add_argument(
        "--provider",
        choices=["csv", "polymarket", "polymarket-archive", "pendle"],
        default="csv",
        help="Data source to use. CSV runs detection; archive providers expose real data files.",
    )
    parser.add_argument("--input", help="Path to normalized order-event CSV.")
    parser.add_argument("--economics", help="Optional account economics CSV with maker, subsidy, cost, capital, period_days.")
    parser.add_argument("--mode", choices=["orders", "accounts"], default="orders", help="Print order-level or account-level results.")
    parser.add_argument("--list-snapshots", action="store_true", help="List files available from a real archive provider.")
    parser.add_argument("--download-snapshot", help="Download one archive snapshot by exact file name.")
    parser.add_argument("--output-dir", default="data/raw", help="Directory for downloaded archive snapshots.")
    parser.add_argument("--top", type=int, default=10, help="Number of highest-risk orders to print.")
    parser.add_argument("--list-incentives", action="store_true", help="List Pendle limit-order incentive configs.")
    parser.add_argument("--list-orders", action="store_true", help="List raw Pendle limit orders.")
    parser.add_argument("--order-book", action="store_true", help="List Pendle aggregated limit-order book entries.")
    parser.add_argument("--chain-id", type=int, help="Pendle chain ID, for example 42161 for Arbitrum.")
    parser.add_argument("--market", help="Pendle market address for --order-book.")
    parser.add_argument("--token-id", help="Polymarket CLOB token ID for --order-book.")
    parser.add_argument("--maker", help="Optional Pendle maker address filter for --list-orders.")
    parser.add_argument("--active", choices=["true", "false", "all"], default="true", help="Pendle active-order filter.")
    args = parser.parse_args()

    if args.provider == "polymarket-archive":
        _run_polymarket_archive(args)
        return

    if args.provider == "polymarket":
        _run_polymarket_live(args)
        return

    if args.provider == "pendle":
        _run_pendle(args)
        return

    if not args.input:
        parser.error("--input is required when --provider csv")

    provider = CsvOrderEventProvider(Path(args.input))
    pipeline = DetectionPipeline(provider)
    if args.mode == "accounts":
        economics = load_account_economics(args.economics) if args.economics else None
        results = pipeline.run_accounts(economics=economics)
        print(_format_account_table(results[: args.top]))
    else:
        results = pipeline.run()
        print(_format_order_table(results[: args.top]))


def _run_polymarket_archive(args) -> None:
    provider = PolymarketProvider()
    snapshots = provider.list_snapshots()

    if args.download_snapshot:
        by_name = {snapshot.name: snapshot for snapshot in snapshots}
        snapshot = by_name.get(args.download_snapshot)
        if snapshot is None:
            available = ", ".join(sorted(by_name)[:10])
            raise SystemExit(f"Snapshot not found: {args.download_snapshot}. First available files: {available}")
        path = provider.download_snapshot(snapshot, args.output_dir)
        print(f"Downloaded {snapshot.name} to {path}")
        return

    if args.list_snapshots:
        print(_format_archive_table(snapshots[: args.top]))
        return

    raise SystemExit(
        "Polymarket archive is a real snapshot source. Use --list-snapshots or --download-snapshot. "
        "Convert downloaded snapshots into normalized order-event CSV before running account detection."
    )


def _run_polymarket_live(args) -> None:
    provider = PolymarketLiveProvider()
    if args.list_orders:
        markets = provider.list_markets(limit=args.top)
        print(_format_polymarket_markets(markets))
        return

    if args.order_book:
        if not args.token_id:
            raise SystemExit("--token-id is required with --provider polymarket --order-book")
        payload = provider.fetch_order_book(token_id=args.token_id)
        print(_format_polymarket_order_book(payload, args.top))
        return

    raise SystemExit(
        "Polymarket live source configured. Use --list-orders to list active Gamma markets with CLOB token IDs, "
        "or --order-book --token-id <clob-token-id> to fetch an aggregated CLOB order book."
    )


def _run_pendle(args) -> None:
    provider = PendleProvider()
    if args.list_incentives:
        configs = provider.list_incentive_configs()
        print(_format_pendle_incentives(configs[: args.top]))
        return

    if args.list_orders:
        is_active = None if args.active == "all" else args.active == "true"
        payload = provider.fetch_limit_orders(
            chain_id=args.chain_id,
            limit=args.top,
            is_active=is_active,
            maker=args.maker,
        )
        print(_format_pendle_orders(payload.get("results", [])))
        return

    if args.order_book:
        if args.chain_id is None or not args.market:
            raise SystemExit("--chain-id and --market are required with --provider pendle --order-book")
        payload = provider.fetch_order_book(chain_id=args.chain_id, market=args.market, limit=args.top)
        print(_format_pendle_order_book(payload, args.top))
        return

    raise SystemExit(
        f"Pendle source configured: {provider.source_url}. Use --list-incentives, --list-orders, or --order-book. "
        "Run detection after converting raw Pendle implied-APY orders into normalized open/cancel/fill events."
    )


def _format_archive_table(rows: list[ArchiveSnapshot]) -> str:
    headers = ["venue", "format", "name", "url"]
    lines = ["  ".join(header.ljust(width) for header, width in zip(headers, _archive_widths()))]
    for row in rows:
        values = [row.venue, row.format, row.name, row.url]
        lines.append("  ".join(value.ljust(width) for value, width in zip(values, _archive_widths())))
    return "\n".join(lines)


def _format_order_table(rows) -> str:
    headers = ["risk", "p_value", "z", "order_id", "maker", "venue", "market", "reasons"]
    lines = ["  ".join(header.ljust(width) for header, width in zip(headers, _order_widths()))]
    for row in rows:
        values = [
            f"{row.risk_score:.4f}",
            f"{row.p_value:.4f}",
            f"{row.z_score:.2f}",
            row.order_id,
            row.maker,
            row.venue,
            row.market,
            ",".join(row.reasons),
        ]
        lines.append("  ".join(value.ljust(width) for value, width in zip(values, _order_widths())))
    return "\n".join(lines)


def _format_account_table(rows) -> str:
    headers = ["risk", "maker", "orders", "avoid", "far_order_ratio", "profit", "apy", "reasons"]
    lines = ["  ".join(header.ljust(width) for header, width in zip(headers, _account_widths()))]
    for row in rows:
        values = [
            f"{row.account_risk_score:.4f}",
            row.maker,
            str(row.order_count),
            f"{row.near_touch_cancel_rate:.2%}",
            f"{row.far_order_ratio:.2%}",
            f"{row.net_profit:.2f}",
            f"{row.annualized_return:.2%}",
            ",".join(row.reasons),
        ]
        lines.append("  ".join(value.ljust(width) for value, width in zip(values, _account_widths())))
    return "\n".join(lines)


def _format_pendle_incentives(rows) -> str:
    headers = ["chain", "market", "implied_apy", "range", "buy_yt_apr", "sell_pt_apr"]
    lines = ["  ".join(header.ljust(width) for header, width in zip(headers, _pendle_incentive_widths()))]
    for row in rows:
        estimated_apr = row.get("estimatedApr") or {}
        values = [
            str(row.get("chainId", "")),
            _shorten(row.get("marketAddress", "")),
            _format_decimal(row.get("impliedApy")),
            _format_decimal((row.get("long") or {}).get("range")),
            _format_decimal(estimated_apr.get("buyYtApr")),
            _format_decimal(estimated_apr.get("sellPtApr")),
        ]
        lines.append("  ".join(value.ljust(width) for value, width in zip(values, _pendle_incentive_widths())))
    return "\n".join(lines)


def _format_pendle_orders(rows) -> str:
    headers = ["id", "chain", "maker", "type", "status", "active", "canceled", "notional_usd", "latest_event"]
    lines = ["  ".join(header.ljust(width) for header, width in zip(headers, _pendle_order_widths()))]
    for row in rows:
        order_state = row.get("orderState") or {}
        values = [
            _shorten(row.get("id", "")),
            str(row.get("chainId", "")),
            _shorten(row.get("maker", "")),
            str(order_state.get("orderType", row.get("type", ""))),
            str(row.get("status", "")),
            str(row.get("isActive", "")),
            str(row.get("isCanceled", "")),
            _format_decimal(order_state.get("notionalVolumeUSD")),
            str(row.get("latestEventTimestamp", "")),
        ]
        lines.append("  ".join(value.ljust(width) for value, width in zip(values, _pendle_order_widths())))
    return "\n".join(lines)


def _format_pendle_order_book(payload, top: int) -> str:
    headers = ["side", "implied_apy", "py_size", "notional_size", "qualified_py_size"]
    lines = ["  ".join(header.ljust(width) for header, width in zip(headers, _pendle_book_widths()))]
    entries = []
    entries.extend(("long", row) for row in payload.get("longYieldEntries", [])[:top])
    entries.extend(("short", row) for row in payload.get("shortYieldEntries", [])[:top])
    for side, row in entries:
        values = [
            side,
            _format_decimal(row.get("impliedApy")),
            _format_decimal(row.get("pySize")),
            _format_decimal(row.get("notionalSize")),
            _format_decimal(row.get("incentiveQualifiedPySize")),
        ]
        lines.append("  ".join(value.ljust(width) for value, width in zip(values, _pendle_book_widths())))
    return "\n".join(lines)


def _format_polymarket_markets(rows) -> str:
    headers = ["id", "question", "tokens", "bid", "ask", "liquidity", "volume24h"]
    lines = ["  ".join(header.ljust(width) for header, width in zip(headers, _polymarket_market_widths()))]
    for row in rows:
        values = [
            str(row.get("id", "")),
            _clip(str(row.get("question", "")), 42),
            _clip(_parse_token_ids(row.get("clobTokenIds")), 34),
            _format_decimal(row.get("bestBid")),
            _format_decimal(row.get("bestAsk")),
            _format_decimal(row.get("liquidityNum", row.get("liquidity"))),
            _format_decimal(row.get("volume24hr")),
        ]
        lines.append("  ".join(value.ljust(width) for value, width in zip(values, _polymarket_market_widths())))
    return "\n".join(lines)


def _format_polymarket_order_book(payload, top: int) -> str:
    headers = ["side", "price", "size", "token_id", "timestamp"]
    lines = ["  ".join(header.ljust(width) for header, width in zip(headers, _polymarket_book_widths()))]
    token_id = payload.get("asset_id", "")
    timestamp = str(payload.get("timestamp", ""))
    for side_name in ("bids", "asks"):
        side = "bid" if side_name == "bids" else "ask"
        for row in payload.get(side_name, [])[:top]:
            values = [
                side,
                _format_decimal(row.get("price")),
                _format_decimal(row.get("size")),
                _shorten(token_id, prefix=10, suffix=6),
                timestamp,
            ]
            lines.append("  ".join(value.ljust(width) for value, width in zip(values, _polymarket_book_widths())))
    return "\n".join(lines)


def _parse_token_ids(value: object) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, list):
        tokens = [str(item) for item in value]
    else:
        try:
            parsed = json.loads(str(value))
            tokens = [str(item) for item in parsed] if isinstance(parsed, list) else [str(value)]
        except (json.JSONDecodeError, TypeError):
            tokens = [str(value)]
    return ",".join(_shorten(token, prefix=6, suffix=6) for token in tokens)


def _clip(value: str, width: int) -> str:
    return value if len(value) <= width else f"{value[: width - 3]}..."


def _shorten(value: object, prefix: int = 8, suffix: int = 4) -> str:
    text = str(value)
    if len(text) <= prefix + suffix + 3:
        return text
    return f"{text[:prefix]}...{text[-suffix:]}"


def _format_decimal(value: object) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):.6g}"
    except (TypeError, ValueError):
        return str(value)


def _order_widths() -> list[int]:
    return [7, 8, 6, 10, 12, 9, 18, 48]


def _account_widths() -> list[int]:
    return [7, 12, 6, 8, 15, 10, 9, 64]


def _archive_widths() -> list[int]:
    return [12, 8, 36, 80]


def _pendle_incentive_widths() -> list[int]:
    return [7, 15, 12, 10, 12, 12]


def _pendle_order_widths() -> list[int]:
    return [15, 7, 15, 16, 12, 8, 9, 13, 24]


def _pendle_book_widths() -> list[int]:
    return [7, 12, 14, 16, 18]


def _polymarket_market_widths() -> list[int]:
    return [8, 44, 36, 8, 8, 11, 10]


def _polymarket_book_widths() -> list[int]:
    return [7, 8, 12, 20, 15]


if __name__ == "__main__":
    main()
