import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from jaytradingbot_scanner.api import app
from jaytradingbot_scanner.chain import ReadOnlyChain

client = TestClient(app)


def test_health_proves_execution_is_disabled() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mode": "fork-simulation-preparation",
        "contract_deployed": False,
        "execution_enabled": False,
        "signing_enabled": False,
        "broadcast_enabled": False,
        "persistent_history_enabled": False,
    }


def test_mutating_http_methods_are_rejected() -> None:
    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)("/api/health")
        assert response.status_code == 405
        assert response.headers["allow"] == "GET, HEAD"


def test_web_adapter_imports_no_execution_capability() -> None:
    api_source = (
        Path(__file__).parents[1]
        / "jaytradingbot_scanner"
        / "api.py"
    ).read_text(encoding="utf-8").lower()
    forbidden = (
        "private_key",
        "send_transaction",
        "send_raw_transaction",
        "sign_transaction",
        "eth_account",
        "from .calldata import",
        "from .monitor import",
    )
    for capability in forbidden:
        assert capability not in api_source


def test_web_import_graph_does_not_load_calldata_capability() -> None:
    probe = (
        "import sys; "
        "import jaytradingbot_scanner.api; "
        "assert 'jaytradingbot_scanner.calldata' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_vercel_uses_fastapi_autodetection_without_manual_function_map() -> None:
    scanner_dir = Path(__file__).parents[1]
    config = json.loads((scanner_dir / "vercel.json").read_text(encoding="utf-8"))
    assert "functions" not in config
    entrypoint = (scanner_dir / "app.py").read_text(encoding="utf-8")
    assert "from jaytradingbot_scanner.api import app" in entrypoint


def test_chain_reader_exposes_no_transaction_methods() -> None:
    public_names = {name.lower() for name in dir(ReadOnlyChain)}
    assert "send_transaction" not in public_names
    assert "send_raw_transaction" not in public_names
    assert "sign_transaction" not in public_names


def test_scan_requires_only_read_only_rpc_configuration(monkeypatch) -> None:
    monkeypatch.delenv("ETHEREUM_RPC_URL", raising=False)
    response = client.get("/api/scan")
    assert response.status_code == 503
    assert response.json() == {
        "error": "ETHEREUM_RPC_URL is not configured",
        "mode": "read-only",
    }


def test_selectable_amount_is_validated_before_rpc(monkeypatch) -> None:
    monkeypatch.delenv("ETHEREUM_RPC_URL", raising=False)
    invalid = {
        "0": "amount_eth must be between 0.001 and 100",
        "0.0009": "amount_eth must be between 0.001 and 100",
        "101": "amount_eth must be between 0.001 and 100",
        "not-a-number": "amount_eth must be a decimal number",
        "NaN": "amount_eth must be finite",
        "0.0010000000000000001": "amount_eth supports at most 18 decimal places",
    }
    for value, message in invalid.items():
        response = client.get("/api/scan", params={"amount_eth": value})
        assert response.status_code == 400
        assert response.json() == {"error": message, "mode": "simulation-only"}


def test_valid_small_amount_reaches_read_only_rpc_gate(monkeypatch) -> None:
    monkeypatch.delenv("ETHEREUM_RPC_URL", raising=False)
    response = client.get("/api/scan", params={"amount_eth": "0.001"})
    assert response.status_code == 503
    assert response.json()["error"] == "ETHEREUM_RPC_URL is not configured"


def test_dashboard_has_no_wallet_or_execution_controls() -> None:
    source = (
        Path(__file__).parents[1]
        / "jaytradingbot_scanner"
        / "dashboard.html"
    ).read_text(encoding="utf-8").lower()
    assert "run read-only simulation" in source
    assert "mainnet execution locked" in source
    for forbidden in ("window.ethereum", "eth_requestaccounts", "sendtransaction"):
        assert forbidden not in source
