from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from spoof_liquidity_detector.accounts import load_account_economics
from spoof_liquidity_detector.evidence import (
    DEFAULT_POLYMARKET_EXCHANGE_CONTRACTS,
    EvmChainEvidenceClient,
    GenericFillEventConfig,
    scan_generic_evm_chain_fills,
    scan_polymarket_chain_fills,
)
from spoof_liquidity_detector.pipeline import DetectionPipeline
from spoof_liquidity_detector.providers import CsvOrderEventProvider

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = Path(__file__).resolve().parent / "web"


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
    return [_serialize_dataclass(row) for row in rows[:top]]


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

    rewards = _load_reward_amounts_from_params(params)
    client = EvmChainEvidenceClient(chain_id=chain_id, rpc_url=rpc_url)
    rows = scan_polymarket_chain_fills(
        client,
        contracts=contracts,
        from_block=from_block,
        to_block=to_block,
        chunk_size=chunk_size,
        rewards=rewards,
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
    rewards = _load_reward_amounts_from_params(params)
    client = EvmChainEvidenceClient(chain_id=chain_id, rpc_url=rpc_url)
    rows = scan_generic_evm_chain_fills(
        client,
        contracts=contracts,
        config=config,
        from_block=from_block,
        to_block=to_block,
        chunk_size=chunk_size,
        rewards=rewards,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Spoof Liquidity Detector local UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
