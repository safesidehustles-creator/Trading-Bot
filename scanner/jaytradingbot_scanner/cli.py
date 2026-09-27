from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict

from .chain import ReadOnlyChain
from .calldata import build_unsigned_call
from .config import load_config
from .discovery import build_default_cycles
from .engine import OpportunityEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only JayTradingBot scanner")
    parser.add_argument("--config", default="scanner/config.example.json")
    parser.add_argument("--contract", help="Deployed bot address used only as unsigned call target")
    parser.add_argument("--profit-recipient", help="Recipient encoded into unsigned calldata")
    parser.add_argument("--deadline-seconds", type=int, default=120)
    parser.add_argument(
        "--discover",
        action="store_true",
        help="quote allowlisted venues, stablecoins, fee tiers, and 0.001-1 WETH sizes",
    )
    args = parser.parse_args()

    rpc_url = os.environ.get("ETHEREUM_RPC_URL")
    if not rpc_url:
        raise SystemExit("ETHEREUM_RPC_URL is required; no private key is used")

    provider, policy, cycles = load_config(args.config)
    if args.discover:
        cycles = list(build_default_cycles())
    chain = ReadOnlyChain(rpc_url)
    engine = OpportunityEngine(chain.quote_leg)
    premium_bps = chain.aave_premium_bps(provider)

    if bool(args.contract) != bool(args.profit_recipient):
        raise SystemExit("--contract and --profit-recipient must be provided together")

    results = []
    gas_price_wei = chain.gas_price_wei
    for cycle in cycles:
        try:
            result = engine.evaluate(cycle, policy, premium_bps, gas_price_wei)
            item = asdict(result)
            if result.executable and args.contract:
                item["unsigned_call"] = build_unsigned_call(
                    cycle=cycle,
                    result=result,
                    contract_address=args.contract,
                    profit_recipient=args.profit_recipient,
                    minimum_profit=policy.minimum_profit,
                    deadline=int(time.time()) + args.deadline_seconds,
                ).to_dict()
        except Exception as exc:
            item = {
                "cycle": cycle.name,
                "amount_in": cycle.amount_in,
                "executable": False,
                "error": str(exc)[:200],
                "rejection_reason": "quote unavailable; candidate skipped",
            }
        results.append(item)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
