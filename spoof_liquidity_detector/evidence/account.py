from __future__ import annotations

from collections import Counter, defaultdict

from spoof_liquidity_detector.schema import AccountChainEvidence, ChainEvidence


def summarize_account_chain_evidence(evidence_rows: list[ChainEvidence]) -> dict[str, AccountChainEvidence]:
    grouped: dict[str, list[ChainEvidence]] = defaultdict(list)
    for row in evidence_rows:
        if row.maker:
            grouped[row.maker].append(row)

    summaries: dict[str, AccountChainEvidence] = {}
    for maker, rows in grouped.items():
        event_counts = Counter(event.event_name for row in rows for event in row.events)
        filled_notional = sum(
            float(event.notional_volume or 0)
            for row in rows
            for event in row.events
            if event.event_name == "OrderFilledV2"
        )
        summaries[maker] = AccountChainEvidence(
            maker=maker,
            order_count=len(rows),
            confirmed_order_count=sum(1 for row in rows if row.order_linked),
            matched_log_count=sum(row.matched_log_count for row in rows),
            fill_event_count=event_counts.get("OrderFilledV2", 0),
            filled_notional=filled_notional,
            blocks=tuple(sorted({block for row in rows for block in row.blocks})),
            contracts=tuple(sorted({contract for row in rows for contract in row.contracts})),
            event_counts=dict(event_counts),
        )
    return summaries
