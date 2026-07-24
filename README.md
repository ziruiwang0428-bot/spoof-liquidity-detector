# Spoof Liquidity Detector

Blue-team research framework for detecting suspicious fleeting liquidity in crypto limit-order markets.

The project scores both order-level behavior and maker/account-level behavior. It is designed to identify accounts that may post liquidity far from the market, avoid execution when price approaches, and still earn liquidity incentives after costs.

## Current Real Data Sources

- Pendle limit-order app: https://app.pendle.finance/limit-order
- Polymarket PMXT archive: https://archive.pmxt.dev/Polymarket/v2/

Important distinction:

- The Polymarket PMXT URL is a real archive endpoint. The CLI can list and download archive snapshots from it.
- The Pendle app uses public backend endpoints under `https://api-v2.pendle.finance/bff`. The CLI can fetch raw incentive configs, raw limit orders, and aggregated order-book entries from those endpoints.
- To run the spoof-liquidity detector itself on Pendle, raw implied-APY limit-order responses still need to be converted into the normalized open/cancel/fill event schema below.

## Quick Start

Run the account-level demo with bundled sample data:

```bash
python -m spoof_liquidity_detector.cli --input data/sample_order_events.csv --economics data/sample_account_economics.csv --mode accounts --top 10
```

List real Polymarket archive snapshots:

```bash
python -m spoof_liquidity_detector.cli --provider polymarket-archive --list-snapshots --top 20
```

Download one real Polymarket archive snapshot:

```bash
python -m spoof_liquidity_detector.cli --provider polymarket-archive --download-snapshot <snapshot-name> --output-dir data/raw
```

Check the configured Pendle source:

```bash
python -m spoof_liquidity_detector.cli --provider pendle --list-incentives --top 10
```

List recent raw Pendle limit orders:

```bash
python -m spoof_liquidity_detector.cli --provider pendle --list-orders --chain-id 42161 --active true --top 10
```

List a Pendle market order book:

```bash
python -m spoof_liquidity_detector.cli --provider pendle --order-book --chain-id 42161 --market <market-address> --top 10
```

## Detection Metrics

Order-level metrics:

- `distance_bps`: order price distance from mid price
- `lifetime_seconds`: time from open to cancel/fill
- `cancelled`: whether the order was cancelled
- `approach_bps`: distance from best quote when the order was cancelled
- `notional`: price times quantity
- `risk_score`: interpretable order-level risk score

Account-level metrics:

- `avoid`: share of total orders cancelled near execution
- `far_order_ratio`: far-from-mid orders divided by total orders
- `profit`: subsidy minus cost
- `apy`: annualized return based on profit, capital, and period length
- `reasons`: explanations for why the account is suspicious

The current account-level hypothesis is:

```text
fake-liquidity risk = avoids execution + posts far from mid + earns subsidy after cost + high annualized return
```

## Normalized Order Event Schema

Real data should be converted to this CSV format before running detection:

| Field | Description |
| --- | --- |
| `venue` | Trading venue, for example `pendle` or `polymarket` |
| `market` | Market or contract |
| `order_id` | Unique order ID |
| `maker` | Maker address or account |
| `side` | `buy` or `sell` |
| `price` | Order price |
| `quantity` | Order quantity |
| `event_type` | `open`, `cancel`, or `fill` |
| `timestamp` | ISO timestamp |
| `mid_price` | Mid price at event time |
| `best_bid` | Best bid at event time |
| `best_ask` | Best ask at event time |

Optional account economics CSV:

| Field | Description |
| --- | --- |
| `maker` | Maker address or account |
| `subsidy` | Liquidity incentive earned |
| `cost` | Estimated trading, gas, inventory, or hedging cost |
| `capital` | Capital used by the account |
| `period_days` | Measurement period in days |

## Project Structure

```text
spoof_liquidity_detector/
  accounts/                 # Maker/account-level economics and risk profiling
  features/                 # Order lifecycle feature engineering
  providers/                # CSV, Pendle backend, and Polymarket archive providers
  statistics/               # Order-level statistical scoring
  cli.py                    # Command-line entry point
  pipeline.py               # Detection pipeline
  schema.py                 # Shared data models
data/
  sample_order_events.csv
  sample_account_economics.csv
tests/
  test_*.py
```

## Compliance Note

This repository produces risk signals for market-integrity research. A high score is not proof of misconduct. Use the output for review, investigation, and liquidity incentive audits.
