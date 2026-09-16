from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from .chain import ReadOnlyChain
from .config import load_config
from .engine import OpportunityEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only JayTradingBot scanner")
    parser.add_argument("--config", default="scanner/config.example.json")
    args = parser.parse_args()

    rpc_url = os.environ.get("ETHEREUM_RPC_URL")
    if not rpc_url:
        raise SystemExit("ETHEREUM_RPC_URL is required; no private key is used")

    provider, policy, cycles = load_config(args.config)
    chain = ReadOnlyChain(rpc_url)
    engine = OpportunityEngine(chain.quote_leg)
    premium_bps = chain.aave_premium_bps(provider)

    results = [
        asdict(engine.evaluate(cycle, policy, premium_bps, chain.gas_price_wei))
        for cycle in cycles
    ]
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
