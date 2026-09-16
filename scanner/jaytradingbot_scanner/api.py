from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .chain import ReadOnlyChain
from .config import load_config
from .engine import OpportunityEngine

PACKAGE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PACKAGE_DIR.parent / "config.example.json"

app = FastAPI(
    title="JayTradingBot Read-Only Monitor",
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


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse((PACKAGE_DIR / "dashboard.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "mode": "read-only",
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
def scan() -> JSONResponse:
    """Run one stateless quote pass. No calldata, signing, or sending is available."""
    rpc_url = os.environ.get("ETHEREUM_RPC_URL")
    if not rpc_url:
        return JSONResponse(
            {"error": "ETHEREUM_RPC_URL is not configured", "mode": "read-only"},
            status_code=503,
        )

    try:
        provider, policy, cycles = load_config(str(CONFIG_PATH))
        chain = ReadOnlyChain(rpc_url)
        engine = OpportunityEngine(chain.quote_leg)
        premium_bps = chain.aave_premium_bps(provider)
        payload = [
            asdict(engine.evaluate(cycle, policy, premium_bps, chain.gas_price_wei))
            for cycle in cycles
        ]
        return JSONResponse(
            {
                "mode": "read-only",
                "execution_enabled": False,
                "signing_enabled": False,
                "broadcast_enabled": False,
                "results": payload,
            }
        )
    except Exception as exc:
        return JSONResponse(
            {"error": str(exc)[:300], "mode": "read-only"},
            status_code=503,
        )
