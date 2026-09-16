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

The example route is expected to be rejected under normal conditions because it round-trips through fees. That is a safety test, not a profit opportunity.

## Safety boundary

There is intentionally no private-key setting, transaction signer, deployment command, or automatic executor. Rejected routes cannot produce normal call data; only the clearly marked `simulation_only` path can encode a known losing route for a safety test. Real broadcasting remains disabled during development.
