from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.request import Request, urlopen

from .engine import OpportunityEngine
from .models import Cycle, QuoteResult, ScanPolicy


class ChainReader(Protocol):
    @property
    def gas_price_wei(self) -> int: ...
    def aave_premium_bps(self, provider: str) -> int: ...
    def quote_leg(self, leg: object, amount_in: int) -> int: ...


class AlertSink(Protocol):
    def send(self, result: QuoteResult) -> None: ...


class ConsoleAlertSink:
    def send(self, result: QuoteResult) -> None:
        print(json.dumps({"type": "opportunity", **asdict(result)}, default=list))


class DiscordWebhookSink:
    """Optional alert-only webhook. It cannot control or execute the bot."""

    def __init__(self, webhook_url: str, timeout: int = 10) -> None:
        if not webhook_url.startswith("https://"):
            raise ValueError("Discord webhook must use HTTPS")
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send(self, result: QuoteResult) -> None:
        body = {
            "content": (
                f"JayTradingBot read-only opportunity: **{result.cycle}**\n"
                f"Protected net profit: `{result.net_profit}` asset units\n"
                "Simulation required. No transaction was sent."
            )
        }
        request = Request(
            self.webhook_url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:  # noqa: S310
            if not 200 <= response.status < 300:
                raise RuntimeError(f"Discord returned HTTP {response.status}")


class OpportunityStore:
    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scanned_at TEXT NOT NULL,
                cycle TEXT NOT NULL,
                executable INTEGER NOT NULL,
                net_profit TEXT,
                gas_cost TEXT,
                quoted_amount_out TEXT,
                rejection_reason TEXT,
                error TEXT
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_state (
                cycle TEXT PRIMARY KEY,
                last_alerted_at INTEGER NOT NULL
            )
            """
        )
        self.connection.commit()

    def record_result(self, result: QuoteResult, scanned_at: datetime) -> None:
        self.connection.execute(
            """
            INSERT INTO scan_results (
                scanned_at, cycle, executable, net_profit, gas_cost,
                quoted_amount_out, rejection_reason, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                scanned_at.isoformat(),
                result.cycle,
                int(result.executable),
                str(result.net_profit),
                str(result.gas_cost),
                str(result.quoted_amount_out),
                result.rejection_reason,
            ),
        )
        self.connection.commit()

    def record_error(self, cycle: str, error: str, scanned_at: datetime) -> None:
        self.connection.execute(
            """
            INSERT INTO scan_results (
                scanned_at, cycle, executable, rejection_reason, error
            ) VALUES (?, ?, 0, 'quote error', ?)
            """,
            (scanned_at.isoformat(), cycle, error[:500]),
        )
        self.connection.commit()

    def alert_due(self, cycle: str, now_epoch: int, cooldown_seconds: int) -> bool:
        row = self.connection.execute(
            "SELECT last_alerted_at FROM alert_state WHERE cycle = ?", (cycle,)
        ).fetchone()
        return row is None or now_epoch - int(row[0]) >= cooldown_seconds

    def mark_alerted(self, cycle: str, now_epoch: int) -> None:
        self.connection.execute(
            """
            INSERT INTO alert_state (cycle, last_alerted_at) VALUES (?, ?)
            ON CONFLICT(cycle) DO UPDATE SET last_alerted_at = excluded.last_alerted_at
            """,
            (cycle, now_epoch),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


class MonitorService:
    def __init__(
        self,
        chain: ChainReader,
        provider: str,
        policy: ScanPolicy,
        cycles: list[Cycle],
        store: OpportunityStore,
        sinks: list[AlertSink],
        cooldown_seconds: int = 300,
    ) -> None:
        if cooldown_seconds < 0:
            raise ValueError("cooldown must not be negative")
        self.chain = chain
        self.provider = provider
        self.policy = policy
        self.cycles = cycles
        self.store = store
        self.sinks = sinks
        self.cooldown_seconds = cooldown_seconds
        self.engine = OpportunityEngine(chain.quote_leg)

    def run_once(self, now_epoch: int | None = None) -> list[QuoteResult]:
        epoch = int(time.time()) if now_epoch is None else now_epoch
        scanned_at = datetime.fromtimestamp(epoch, tz=UTC)
        premium_bps = self.chain.aave_premium_bps(self.provider)
        gas_price = self.chain.gas_price_wei
        results: list[QuoteResult] = []

        for cycle in self.cycles:
            try:
                result = self.engine.evaluate(cycle, self.policy, premium_bps, gas_price)
                self.store.record_result(result, scanned_at)
                results.append(result)
                if result.executable and self.store.alert_due(
                    cycle.name, epoch, self.cooldown_seconds
                ):
                    for sink in self.sinks:
                        sink.send(result)
                    self.store.mark_alerted(cycle.name, epoch)
            except Exception as exc:  # one quote must not stop other routes
                self.store.record_error(cycle.name, str(exc), scanned_at)
        return results

    def run_forever(self, interval_seconds: int) -> None:
        if interval_seconds < 10:
            raise ValueError("monitor interval must be at least 10 seconds")
        while True:
            self.run_once()
            time.sleep(interval_seconds)
