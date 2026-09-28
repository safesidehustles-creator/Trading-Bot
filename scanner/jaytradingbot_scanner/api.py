from __future__ import annotations

import os
from functools import lru_cache
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .chain import ReadOnlyChain
from .config import load_config
from .discovery import build_web_cycles
from .engine import OpportunityEngine

PACKAGE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PACKAGE_DIR.parent / "config.example.json"
WEI_PER_ETH = Decimal(10**18)
MIN_SIMULATION_ETH = Decimal("0.001")
MAX_SIMULATION_ETH = Decimal("100")

app = FastAPI(
    title="JayTradingBot Fork Simulation Monitor",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def enforce_read_only(request: Request, call_next):
    if request.method not in {"GET", "HEAD"}:
        return JSONResponse(
            {"error": "read-only service; mutating methods are disabled"},
            status_code=405,
            headers={"Allow": "GET, HEAD"},
        )
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'"
    )
    return response


def _simulation_amount_wei(amount_eth: str | None) -> int | None:
    if amount_eth is None:
        return None
    try:
        amount = Decimal(amount_eth)
    except InvalidOperation as exc:
        raise ValueError("amount_eth must be a decimal number") from exc
    if not amount.is_finite():
        raise ValueError("amount_eth must be finite")
    if amount < MIN_SIMULATION_ETH or amount > MAX_SIMULATION_ETH:
        raise ValueError(
            f"amount_eth must be between {MIN_SIMULATION_ETH} and {MAX_SIMULATION_ETH}"
        )
    amount_wei = amount * WEI_PER_ETH
    if amount_wei != amount_wei.to_integral_value():
        raise ValueError("amount_eth supports at most 18 decimal places")
    return int(amount_wei)


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse((PACKAGE_DIR / "dashboard.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "mode": "fork-simulation-preparation",
        "contract_deployed": False,
        "execution_enabled": False,
        "signing_enabled": False,
        "broadcast_enabled": False,
        "persistent_history_enabled": False,
    }


@app.get("/api/summary")
def summary() -> dict[str, object]:
    return {
        "total_scans": 0,
        "opportunities": 0,
        "errors": 0,
        "last_scan": None,
        "routes_alerted": 0,
        "mode": "read-only-stateless",
        "execution_enabled": False,
    }


@app.get("/api/results")
def results() -> list[object]:
    return []


@app.get("/api/routes")
def routes() -> list[object]:
    return []


@app.get("/api/alerts")
def alerts() -> list[object]:
    return []


@app.get("/api/scan")
def scan(amount_eth: str | None = None) -> JSONResponse:
    """Quote a selectable WETH flash-loan size without signing or sending."""
    try:
        amount_wei = _simulation_amount_wei(amount_eth)
    except ValueError as exc:
        return JSONResponse(
            {"error": str(exc), "mode": "simulation-only"},
            status_code=400,
        )

    rpc_url = os.environ.get("ETHEREUM_RPC_URL")
    if not rpc_url:
        return JSONResponse(
            {"error": "ETHEREUM_RPC_URL is not configured", "mode": "read-only"},
            status_code=503,
        )

    try:
        provider, policy, _configured_cycles = load_config(str(CONFIG_PATH))
        selected_amount = amount_wei or 10**16
        cycles = build_web_cycles(selected_amount)
        chain = ReadOnlyChain(rpc_url)
        engine = OpportunityEngine(lru_cache(maxsize=4096)(chain.quote_leg))
        premium_bps = chain.aave_premium_bps(provider)
        gas_price_wei = chain.gas_price_wei
        payload: list[dict[str, object]] = []
        for cycle in cycles:
            try:
                payload.append(
                    asdict(engine.evaluate(cycle, policy, premium_bps, gas_price_wei))
                )
            except Exception as exc:
                payload.append({
                    "cycle": cycle.name,
                    "amount_in": cycle.amount_in,
                    "executable": False,
                    "error": str(exc)[:200],
                    "rejection_reason": "quote unavailable; candidate skipped",
                })
        return JSONResponse(
            {
                "mode": "simulation-only",
                "flash_loan_amount_eth": amount_eth or "0.01",
                "candidates_scanned": len(cycles),
                "deposit_required": False,
                "execution_enabled": False,
                "signing_enabled": False,
                "broadcast_enabled": False,
                "results": payload,
            }
        )
    except Exception as exc:
        return JSONResponse(
            {"error": str(exc)[:300], "mode": "simulation-only"},
            status_code=503,
        )
