from __future__ import annotations

import argparse
import os

from .chain import ReadOnlyChain
from .config import load_config
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
    args = parser.parse_args()

    rpc_url = os.environ.get("ETHEREUM_RPC_URL")
    if not rpc_url:
        raise SystemExit("ETHEREUM_RPC_URL is required; no private key is used")

    provider, policy, cycles = load_config(args.config)
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
