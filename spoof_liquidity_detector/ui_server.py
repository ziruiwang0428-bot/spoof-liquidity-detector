from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from spoof_liquidity_detector.accounts import AccountProfiler, load_account_economics
from spoof_liquidity_detector.evidence import (
    DEFAULT_POLYMARKET_EXCHANGE_CONTRACTS,
    DEFAULT_POLYMARKET_REWARD_DISTRIBUTORS,
    DEFAULT_POLYMARKET_REWARD_TOKENS,
    EvmChainEvidenceClient,
    GenericFillEventConfig,
    scan_erc20_reward_transfers,
    scan_generic_evm_chain_fills,
    scan_polymarket_chain_fills,
    summarize_account_chain_evidence,
)
from spoof_liquidity_detector.pipeline import DetectionPipeline
from spoof_liquidity_detector.providers import CsvOrderEventProvider, OrderEventProvider, PendleProvider
from spoof_liquidity_detector.schema import OrderEvent

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = Path(__file__).resolve().parent / "web"
DEFAULT_PENDLE_EVIDENCE_CONTRACTS = {
    42161: ["0x000000000000c9B3E2C3Ec88B1B4c0cD853f4321"],
}
class _LoadedOrderEventProvider(OrderEventProvider):
    def __init__(self, events: list[OrderEvent]) -> None:
        self.events = events

    def load_events(self) -> list[OrderEvent]:
        return self.events


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    handler = _make_handler(WEB_ROOT)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Spoof Liquidity Detector UI running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping UI server.")


def sample_account_profiles(top: int = 10, root: Path = PROJECT_ROOT) -> list[dict[str, Any]]:
    provider = CsvOrderEventProvider(root / "data" / "sample_order_events.csv")
    economics = load_account_economics(root / "data" / "sample_account_economics.csv")
    rows = DetectionPipeline(provider).run_accounts(economics=economics)
    payload = []
    for row in rows[:top]:
        item = _serialize_dataclass(row)
        item["evidence_mode"] = "sample_data"
        payload.append(item)
    return payload


def pendle_account_profiles(params: dict[str, list[str]]) -> list[dict[str, Any]]:
    chain_id = _int_param(params, "chain_id", 42161)
    top = _int_param(params, "top", 10)
    fetch_limit = _int_param(params, "fetch_limit", 100)
    lookback_days = _float_param(params, "lookback_days", 7.0)
    max_pages = _int_param(params, "max_pages", 25)
    confirm_chain = _bool_param(params, "confirm_chain", False)
    rpc_url = _str_param(params, "rpc_url", "") or None

    provider = PendleProvider(
        chain_id=chain_id,
        order_limit=fetch_limit,
        lookback_days=lookback_days,
        max_pages=max_pages,
    )
    orders = provider.fetch_detection_orders()
    events = provider.events_from_orders(orders)
    order_results = DetectionPipeline(_LoadedOrderEventProvider(events)).run()
    profiler = AccountProfiler()
    preliminary = profiler.profile(order_results)
    candidate_makers = [row.maker for row in preliminary[: max(top, 1)]]

    economics = {}
    unavailable_rewards: set[str] = set()
    for maker in candidate_makers:
        try:
            economics.update(provider.fetch_account_economics([maker]))
        except Exception:
            unavailable_rewards.add(maker.lower())

    chain_evidence = None
    if confirm_chain and candidate_makers:
        client = EvmChainEvidenceClient(chain_id=chain_id, rpc_url=rpc_url)
        from_block_value = _str_param(params, "from_block", "").strip()
        event_contracts = params.get("contract") or DEFAULT_PENDLE_EVIDENCE_CONTRACTS.get(chain_id)
        if not from_block_value:
            event_contracts = None
        maker_set = {maker.lower() for maker in candidate_makers}
        evidence_rows = [
            client.confirm_order_payload(
                order,
                venue="pendle",
                event_contracts=event_contracts,
                from_block=_block_param(from_block_value) if from_block_value else None,
                to_block=_block_param(_str_param(params, "to_block", "latest")),
                log_chunk_size=_int_param(params, "chunk_size", 1000),
            )
            for order in orders
            if str(order.get("maker") or "").lower() in maker_set
        ]
        chain_evidence = summarize_account_chain_evidence(evidence_rows)

    rows = profiler.profile(order_results, economics=economics, chain_evidence=chain_evidence)
    payload: list[dict[str, Any]] = []
    for row in rows[:top]:
        item = _serialize_dataclass(row)
        item["evidence_mode"] = "chain_plus_api" if confirm_chain else "api_behavior_and_rewards"
        item["reward_status"] = "unavailable" if row.maker.lower() in unavailable_rewards else "verified_api"
        payload.append(item)
    return payload


def polymarket_chain_fills(params: dict[str, list[str]]) -> list[dict[str, Any]]:
    chain_id = _int_param(params, "chain_id", 137)
    from_block = _required_int_param(params, "from_block")
    to_block = _block_param(_str_param(params, "to_block", "latest"))
    top = _int_param(params, "top", 10)
    chunk_size = _int_param(params, "chunk_size", 1000)
    rpc_url = _str_param(params, "rpc_url", "") or None
    contracts = params.get("contract") or DEFAULT_POLYMARKET_EXCHANGE_CONTRACTS.get(chain_id)
    if not contracts:
        raise ValueError(f"No Polymarket contracts configured for chain_id={chain_id}.")

    client = EvmChainEvidenceClient(chain_id=chain_id, rpc_url=rpc_url)
    observation_days = _observation_days(client, from_block, to_block)
    rewards = _load_reward_amounts_from_params(params)
    if rewards is None and _bool_param(params, "scan_chain_rewards", True):
        rewards = scan_erc20_reward_transfers(
            client,
            token_contracts=params.get("reward_token") or DEFAULT_POLYMARKET_REWARD_TOKENS,
            distributor_addresses=params.get("reward_distributor") or DEFAULT_POLYMARKET_REWARD_DISTRIBUTORS,
            from_block=from_block,
            to_block=to_block,
            chunk_size=chunk_size,
        )
    rows = scan_polymarket_chain_fills(
        client,
        contracts=contracts,
        from_block=from_block,
        to_block=to_block,
        chunk_size=chunk_size,
        rewards=rewards,
        observation_days=observation_days,
    )
    return [_serialize_dataclass(row) for row in rows[:top]]


def generic_evm_chain_fills(params: dict[str, list[str]]) -> list[dict[str, Any]]:
    chain_id = _required_int_param(params, "chain_id")
    from_block = _required_int_param(params, "from_block")
    to_block = _block_param(_str_param(params, "to_block", "latest"))
    top = _int_param(params, "top", 10)
    chunk_size = _int_param(params, "chunk_size", 1000)
    rpc_url = _str_param(params, "rpc_url", "") or None
    contracts = params.get("contract") or []
    if not contracts:
        raise ValueError("contract is required for generic EVM scans")

    config = GenericFillEventConfig(
        venue=_str_param(params, "venue", "custom-evm"),
        event_topic=_required_str_param(params, "fill_topic").lower(),
        maker_topic_index=_int_param(params, "maker_topic_index", 2),
        taker_topic_index=_int_param(params, "taker_topic_index", 3),
        maker_amount_word=_int_param(params, "maker_amount_word", 2),
        taker_amount_word=_int_param(params, "taker_amount_word", 3),
        fee_word=_optional_word_param(params, "fee_word", 4),
        notional_source=_str_param(params, "notional_source", "max"),  # type: ignore[arg-type]
        amount_decimals=_int_param(params, "amount_decimals", 6),
    )
    client = EvmChainEvidenceClient(chain_id=chain_id, rpc_url=rpc_url)
    observation_days = _observation_days(client, from_block, to_block)
    rewards = _load_reward_amounts_from_params(params)
    reward_tokens = params.get("reward_token") or []
    reward_distributors = params.get("reward_distributor") or []
    if (
        rewards is None
        and _bool_param(params, "scan_chain_rewards", True)
        and reward_tokens
        and reward_distributors
    ):
        rewards = scan_erc20_reward_transfers(
            client,
            token_contracts=reward_tokens,
            distributor_addresses=reward_distributors,
            from_block=from_block,
            to_block=to_block,
            chunk_size=chunk_size,
            amount_decimals=_int_param(params, "reward_decimals", 6),
        )
    rows = scan_generic_evm_chain_fills(
        client,
        contracts=contracts,
        config=config,
        from_block=from_block,
        to_block=to_block,
        chunk_size=chunk_size,
        rewards=rewards,
        observation_days=observation_days,
    )
    return [_serialize_dataclass(row) for row in rows[:top]]


def _make_handler(web_root: Path):
    class UiHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_root), **kwargs)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                self._handle_api(parsed.path, parse_qs(parsed.query))
                return
            if parsed.path == "/":
                self.path = "/index.html"
            super().do_GET()

        def _handle_api(self, path: str, params: dict[str, list[str]]) -> None:
            try:
                if path == "/api/sample/accounts":
                    payload = {"rows": sample_account_profiles(top=_int_param(params, "top", 10))}
                elif path == "/api/pendle/accounts":
                    payload = {"rows": pendle_account_profiles(params)}
                elif path == "/api/polymarket/fills":
                    payload = {"rows": polymarket_chain_fills(params)}
                elif path == "/api/evm/fills":
                    payload = {"rows": generic_evm_chain_fills(params)}
                else:
                    self.send_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")
                    return
                self._send_json(payload)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return UiHandler


def _serialize_dataclass(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    return dict(value)


def _json_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    if value == float("inf"):
        return "inf"
    return value


def _int_param(params: dict[str, list[str]], name: str, default: int) -> int:
    value = params.get(name, [str(default)])[0]
    return int(value)


def _float_param(params: dict[str, list[str]], name: str, default: float) -> float:
    value = params.get(name, [str(default)])[0]
    return float(value)


def _bool_param(params: dict[str, list[str]], name: str, default: bool) -> bool:
    value = params.get(name, [str(default).lower()])[0].strip().lower()
    return value in {"1", "true", "yes", "on"}


def _required_int_param(params: dict[str, list[str]], name: str) -> int:
    value = params.get(name, [""])[0]
    if not value:
        raise ValueError(f"{name} is required")
    return int(value)


def _required_str_param(params: dict[str, list[str]], name: str) -> str:
    value = params.get(name, [""])[0].strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _str_param(params: dict[str, list[str]], name: str, default: str) -> str:
    return params.get(name, [default])[0]


def _optional_word_param(params: dict[str, list[str]], name: str, default: int) -> int | None:
    value = _int_param(params, name, default)
    return None if value < 0 else value


def _load_reward_amounts_from_params(params: dict[str, list[str]]) -> dict[str, float] | None:
    path_value = _str_param(params, "economics_path", "").strip()
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    economics = load_account_economics(path)
    return {maker.lower(): row.subsidy for maker, row in economics.items()}


def _block_param(value: str) -> int | str:
    if value in {"earliest", "latest", "pending", "safe", "finalized"}:
        return value
    if value.startswith("0x"):
        return int(value, 16)
    return int(value)


def _observation_days(
    client: EvmChainEvidenceClient,
    from_block: int,
    to_block: int | str,
) -> float:
    resolved_to_block = client.block_number() if isinstance(to_block, str) else to_block
    if resolved_to_block < from_block:
        raise ValueError("to_block must be greater than or equal to from_block")
    start_timestamp = client.block_timestamp(from_block)
    end_timestamp = client.block_timestamp(resolved_to_block)
    return max(end_timestamp - start_timestamp, 0) / 86_400


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Spoof Liquidity Detector local UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
