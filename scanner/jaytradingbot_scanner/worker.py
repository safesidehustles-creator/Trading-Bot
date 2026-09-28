from __future__ import annotations

import os
import sys

from .monitor_cli import main as monitor_main


def build_worker_args() -> list[str]:
    """Build validated monitor CLI arguments from deployment configuration."""
    return [
        "jay-monitor",
        "--config",
        os.environ.get("SCANNER_CONFIG", "scanner/config.example.json"),
        "--database",
        os.environ.get("SCANNER_DATABASE", "/data/opportunities.db"),
        "--discover",
        "--amount-eth",
        os.environ.get("FLASH_LOAN_AMOUNT_ETH", "0.1"),
        "--interval",
        os.environ.get("SCAN_INTERVAL_SECONDS", "10"),
        "--cooldown",
        os.environ.get("ALERT_COOLDOWN_SECONDS", "300"),
    ]


def main() -> None:
    sys.argv = build_worker_args()
    monitor_main()


if __name__ == "__main__":
    main()
