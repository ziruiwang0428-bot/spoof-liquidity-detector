from __future__ import annotations

import argparse
from pathlib import Path

from spoof_liquidity_detector.accounts import load_account_economics
from spoof_liquidity_detector.pipeline import DetectionPipeline
from spoof_liquidity_detector.providers import ArchiveSnapshot, CsvOrderEventProvider, PendleProvider, PolymarketProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect suspicious fleeting liquidity from order events.")
    parser.add_argument(
        "--provider",
        choices=["csv", "polymarket-archive", "pendle"],
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
    args = parser.parse_args()

    if args.provider == "polymarket-archive":
        _run_polymarket_archive(args)
        return

    if args.provider == "pendle":
        _run_pendle()
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


def _run_pendle() -> None:
    provider = PendleProvider()
    raise SystemExit(
        f"Pendle source configured: {provider.source_url}. "
        "This is the real limit-order app URL, but it is not a normalized order-event API. "
        "Provide a Pendle API/vendor CSV with open/cancel/fill events via --provider csv --input <file>."
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


def _order_widths() -> list[int]:
    return [7, 8, 6, 10, 12, 9, 18, 48]


def _account_widths() -> list[int]:
    return [7, 12, 6, 8, 15, 10, 9, 64]


def _archive_widths() -> list[int]:
    return [12, 8, 36, 80]


if __name__ == "__main__":
    main()
