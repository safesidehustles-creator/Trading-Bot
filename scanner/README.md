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

The example route is expected to be rejected under normal conditions because it round-trips through fees. That is a safety test, not a profit opportunity.

## Safety boundary

There is intentionally no private-key setting, transaction signer, deployment command, or automatic executor. A later phase can convert an accepted quote into unsigned contract call data for fork simulation, but real broadcasting remains disabled during development.
