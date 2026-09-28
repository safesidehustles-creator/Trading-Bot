from __future__ import annotations

import argparse
import os
from decimal import Decimal, InvalidOperation

from .chain import ReadOnlyChain
from .config import load_config
from .discovery import build_web_cycles
from .monitor import (
    ConsoleAlertSink,
    DiscordWebhookSink,
    MonitorService,
    OpportunityStore,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuous read-only opportunity monitor")
    parser.add_argument("--config", default="scanner/config.example.json")
    parser.add_argument("--database", default="scanner/data/opportunities.db")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--cooldown", type=int, default=300)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="monitor 36 prioritized cross-market routes instead of preset cycles",
    )
    parser.add_argument(
        "--amount-eth",
        default="0.1",
        help="Aave WETH loan size for discovery mode (0.001-100)",
    )
    args = parser.parse_args()

    rpc_url = os.environ.get("ETHEREUM_RPC_URL")
    if not rpc_url:
        raise SystemExit("ETHEREUM_RPC_URL is required; no private key is used")

    provider, policy, cycles = load_config(args.config)
    if args.discover:
        try:
            amount_eth = Decimal(args.amount_eth)
        except InvalidOperation as exc:
            raise SystemExit("--amount-eth must be a decimal number") from exc
        amount_wei = amount_eth * Decimal(10**18)
        if (
            not amount_eth.is_finite()
            or not Decimal("0.001") <= amount_eth <= Decimal("100")
            or amount_wei != amount_wei.to_integral_value()
        ):
            raise SystemExit("--amount-eth must be 0.001-100 with at most 18 decimals")
        cycles = list(build_web_cycles(int(amount_wei)))

    sinks = [ConsoleAlertSink()]
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook:
        sinks.append(DiscordWebhookSink(webhook))

    store = OpportunityStore(args.database)
    service = MonitorService(
        chain=ReadOnlyChain(rpc_url),
        provider=provider,
        policy=policy,
        cycles=cycles,
        store=store,
        sinks=sinks,
        cooldown_seconds=args.cooldown,
    )
    try:
        if args.once:
            service.run_once()
        else:
            service.run_forever(args.interval)
    finally:
        store.close()


if __name__ == "__main__":
    main()
