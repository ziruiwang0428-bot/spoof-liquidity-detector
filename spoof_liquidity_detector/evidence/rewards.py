from __future__ import annotations

from collections import defaultdict

from spoof_liquidity_detector.evidence.evm import EvmChainEvidenceClient

ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
DEFAULT_POLYMARKET_REWARD_TOKENS = [
    "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB",  # pUSD
    "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC.e
]
DEFAULT_POLYMARKET_REWARD_DISTRIBUTORS = [
    "0xc288480574783bd7615170660d71753378159c47",
    "0x1510565e93c9729410b6e41088e014e312fd8829",
    "0xf7cd89be08af4d4d6b1522852ced49fc10169f64",
]


def scan_erc20_reward_transfers(
    client: EvmChainEvidenceClient,
    *,
    token_contracts: list[str],
    distributor_addresses: list[str],
    from_block: int | str,
    to_block: int | str = "latest",
    chunk_size: int | None = 1000,
    amount_decimals: int = 6,
) -> dict[str, float]:
    """Aggregate ERC-20 payouts sent by known reward distributors."""
    rewards: dict[str, float] = defaultdict(float)
    for distributor in distributor_addresses:
        logs = client.get_logs(
            addresses=token_contracts,
            from_block=from_block,
            to_block=to_block,
            chunk_size=chunk_size,
            topics=[ERC20_TRANSFER_TOPIC, _address_topic(distributor)],
        )
        for log in logs:
            recipient, amount = decode_erc20_reward_transfer(log)
            if recipient:
                rewards[recipient] += amount / 10**amount_decimals
    return dict(rewards)


def decode_erc20_reward_transfer(log: dict) -> tuple[str, int]:
    topics = [str(topic).lower() for topic in log.get("topics", [])]
    if len(topics) < 3 or topics[0] != ERC20_TRANSFER_TOPIC:
        return "", 0
    recipient = "0x" + topics[2].removeprefix("0x")[-40:]
    try:
        amount = int(str(log.get("data") or "0x0"), 16)
    except ValueError:
        amount = 0
    return recipient, amount


def _address_topic(address: str) -> str:
    return "0x" + address.lower().removeprefix("0x").rjust(64, "0")
