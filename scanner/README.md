# Read-only opportunity scanner

This scanner reads Ethereum quotes and rejects routes that do not clear all configured costs. It cannot sign or broadcast transactions and does not load a private key.

## Included in phase 1

- Uniswap V2-compatible `getAmountsOut` quotes
- Uniswap V3 Quoter V2 single-pool quotes
- Live Aave flash-loan premium lookup
- Live gas-price lookup
- Route continuity and closed-cycle validation
- Slippage haircut, safety margin, gas, premium, and minimum-profit checks
- JSON output with explicit accept/reject reasons
- Unsigned `startFlashArbitrage` calldata for accepted opportunities
- Explicit refusal to build executable calldata for rejected opportunities

## Run

```bash
cd scanner
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
export ETHEREUM_RPC_URL='YOUR_READ_ONLY_RPC_URL'
pytest -q
jay-scan --config config.example.json
```

To add unsigned call data for accepted results, provide both the target contract and profit recipient:

```bash
jay-scan --config config.example.json \
  --contract 0xYOUR_FORK_DEPLOYMENT \
  --profit-recipient 0xYOUR_TEST_RECIPIENT
```

The output remains unsigned JSON. It is not a transaction and cannot move funds.

## Continuous monitoring

Run one read-only monitoring pass:

```bash
jay-monitor --config config.example.json --once
```

Or continuously scan the configured allowlisted cycles every 60 seconds:

```bash
jay-monitor --config config.example.json --interval 60 --cooldown 300
```

Results are stored in `scanner/data/opportunities.db`. Profitable results print an alert to the console. To add optional Discord alerts, set `DISCORD_WEBHOOK_URL`; the webhook receives a message only and cannot control the bot. Repeated alerts for the same cycle are suppressed during the cooldown.

## Local read-only dashboard

After the monitor has created its database, start the dashboard:

```bash
jay-dashboard --database scanner/data/opportunities.db
```

Open `http://127.0.0.1:8080`. The dashboard shows summary counts, recent scans, route health, estimated net profit, gas costs, rejection reasons, errors, and alert history. It refreshes every 15 seconds.

The server binds only to your device by default and accepts no write or execution operations. Do not expose it publicly without adding authentication and HTTPS.

The example route is expected to be rejected under normal conditions because it round-trips through fees. That is a safety test, not a profit opportunity.

## Safety boundary

There is intentionally no private-key setting, transaction signer, deployment command, or automatic executor. Rejected routes cannot produce normal call data; only the clearly marked `simulation_only` path can encode a known losing route for a safety test. Real broadcasting remains disabled during development.
