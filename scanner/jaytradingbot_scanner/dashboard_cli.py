from __future__ import annotations

import argparse

from .dashboard import DashboardSettings, serve_dashboard


def main() -> None:
    parser = argparse.ArgumentParser(description="Local read-only scanner dashboard")
    parser.add_argument("--database", default="scanner/data/opportunities.db")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("port must be between 1 and 65535")
    serve_dashboard(DashboardSettings(args.database, args.host, args.port))


if __name__ == "__main__":
    main()
