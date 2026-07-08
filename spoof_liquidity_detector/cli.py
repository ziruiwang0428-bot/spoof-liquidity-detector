from __future__ import annotations

import argparse
from pathlib import Path

from spoof_liquidity_detector.pipeline import DetectionPipeline
from spoof_liquidity_detector.providers import CsvOrderEventProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect suspicious fleeting liquidity from order events.")
    parser.add_argument("--input", required=True, help="Path to normalized order-event CSV.")
    parser.add_argument("--top", type=int, default=10, help="Number of highest-risk orders to print.")
    args = parser.parse_args()

    provider = CsvOrderEventProvider(Path(args.input))
    results = DetectionPipeline(provider).run()
    print(_format_table(results[: args.top]))


def _format_table(rows) -> str:
    headers = ["risk", "p_value", "z", "order_id", "maker", "venue", "market", "reasons"]
    lines = ["  ".join(header.ljust(width) for header, width in zip(headers, _widths()))]
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
        lines.append("  ".join(value.ljust(width) for value, width in zip(values, _widths())))
    return "\n".join(lines)


def _widths() -> list[int]:
    return [7, 8, 6, 10, 12, 9, 18, 48]


if __name__ == "__main__":
    main()
