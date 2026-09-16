from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class DashboardSettings:
    database_path: str
    host: str = "127.0.0.1"
    port: int = 8080


class DashboardData:
    """Read-only SQLite queries used by the local dashboard."""

    def __init__(self, database_path: str) -> None:
        path = Path(database_path).resolve()
        if not path.exists():
            raise FileNotFoundError(
                f"monitor database not found: {path}; run jay-monitor --once first"
            )
        self.connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row

    def summary(self) -> dict[str, object]:
        row = self.connection.execute(
            """
            SELECT
                COUNT(*) AS total_scans,
                SUM(CASE WHEN executable = 1 THEN 1 ELSE 0 END) AS opportunities,
                SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) AS errors,
                MAX(scanned_at) AS last_scan
            FROM scan_results
            """
        ).fetchone()
        alerts = self.connection.execute(
            "SELECT COUNT(*) AS count FROM alert_state"
        ).fetchone()
        return {
            "total_scans": int(row["total_scans"] or 0),
            "opportunities": int(row["opportunities"] or 0),
            "errors": int(row["errors"] or 0),
            "last_scan": row["last_scan"],
            "routes_alerted": int(alerts["count"] or 0),
            "mode": "read-only",
            "execution_enabled": False,
        }

    def recent_results(
        self, limit: int = 100, status: str = "all"
    ) -> list[dict[str, object]]:
        safe_limit = min(max(limit, 1), 500)
        where = ""
        params: list[object] = []
        if status == "opportunity":
            where = "WHERE executable = 1 AND error IS NULL"
        elif status == "rejected":
            where = "WHERE executable = 0 AND error IS NULL"
        elif status == "error":
            where = "WHERE error IS NOT NULL"
        elif status != "all":
            raise ValueError("status must be all, opportunity, rejected, or error")
        params.append(safe_limit)
        rows = self.connection.execute(
            f"""
            SELECT id, scanned_at, cycle, executable, net_profit, gas_cost,
                   quoted_amount_out, rejection_reason, error
            FROM scan_results
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,  # nosec B608: where is selected from fixed constants above
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def route_health(self) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT cycle, executable, net_profit, error, scanned_at
            FROM scan_results
            ORDER BY id ASC
            """
        ).fetchall()
        grouped: dict[str, dict[str, object]] = {}
        for row in rows:
            item = grouped.setdefault(
                row["cycle"],
                {
                    "cycle": row["cycle"],
                    "scans": 0,
                    "opportunities": 0,
                    "errors": 0,
                    "best_net_profit": None,
                    "last_scanned_at": None,
                    "last_status": "unknown",
                },
            )
            item["scans"] = int(item["scans"]) + 1
            if row["error"] is not None:
                item["errors"] = int(item["errors"]) + 1
                status = "error"
            elif row["executable"]:
                item["opportunities"] = int(item["opportunities"]) + 1
                status = "opportunity"
            else:
                status = "rejected"
            if row["net_profit"] is not None:
                profit = int(row["net_profit"])
                current = item["best_net_profit"]
                if current is None or profit > int(current):
                    item["best_net_profit"] = str(profit)
            item["last_scanned_at"] = row["scanned_at"]
            item["last_status"] = status
        return list(grouped.values())

    def alert_state(self) -> list[dict[str, object]]:
        rows = self.connection.execute(
            "SELECT cycle, last_alerted_at FROM alert_state ORDER BY cycle"
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.connection.close()


class DashboardHandler(BaseHTTPRequestHandler):
    data: DashboardData
    html_path: Path

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._send_bytes(self.html_path.read_bytes(), "text/html; charset=utf-8")
            elif parsed.path == "/api/summary":
                self._send_json(self.data.summary())
            elif parsed.path == "/api/results":
                query = parse_qs(parsed.query)
                limit = int(query.get("limit", ["100"])[0])
                status = query.get("status", ["all"])[0]
                self._send_json(self.data.recent_results(limit, status))
            elif parsed.path == "/api/routes":
                self._send_json(self.data.route_health())
            elif parsed.path == "/api/alerts":
                self._send_json(self.data.alert_state())
            else:
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except (ValueError, OSError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:  # noqa: N802
        self._send_json(
            {"error": "dashboard is read-only"}, HTTPStatus.METHOD_NOT_ALLOWED
        )

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(
        self, payload: object, status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        self._send_bytes(
            json.dumps(payload).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
        )
        self.end_headers()
        self.wfile.write(body)


def serve_dashboard(settings: DashboardSettings) -> None:
    data = DashboardData(settings.database_path)
    handler = type(
        "ConfiguredDashboardHandler",
        (DashboardHandler,),
        {
            "data": data,
            "html_path": Path(__file__).with_name("dashboard.html"),
        },
    )
    server = ThreadingHTTPServer((settings.host, settings.port), handler)
    print(
        f"JayTradingBot read-only dashboard: http://{settings.host}:{settings.port}\n"
        "Execution is disabled. Press Ctrl+C to stop."
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        data.close()
