from __future__ import annotations

import csv
from pathlib import Path

from spoof_liquidity_detector.schema import AccountEconomics


def load_account_economics(path: str | Path) -> dict[str, AccountEconomics]:
    economics: dict[str, AccountEconomics] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            item = AccountEconomics(
                maker=row["maker"],
                subsidy=float(row.get("subsidy", 0.0)),
                cost=float(row.get("cost", 0.0)),
                capital=float(row.get("capital", 0.0)),
                period_days=float(row.get("period_days", 0.0)),
            )
            economics[item.maker] = item
    return economics
