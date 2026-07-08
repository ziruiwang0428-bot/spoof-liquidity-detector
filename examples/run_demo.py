from __future__ import annotations

from pathlib import Path

from spoof_liquidity_detector.pipeline import DetectionPipeline
from spoof_liquidity_detector.providers import CsvOrderEventProvider


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    provider = CsvOrderEventProvider(root / "data" / "sample_order_events.csv")
    for result in DetectionPipeline(provider).run()[:5]:
        print(
            result.risk_score,
            result.p_value,
            result.order_id,
            result.maker,
            result.reasons,
        )


if __name__ == "__main__":
    main()
