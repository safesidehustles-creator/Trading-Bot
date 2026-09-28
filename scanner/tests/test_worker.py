from pathlib import Path

from jaytradingbot_scanner.worker import build_worker_args


def test_worker_defaults_to_read_only_discovery(monkeypatch) -> None:
    for key in (
        "SCANNER_CONFIG",
        "SCANNER_DATABASE",
        "FLASH_LOAN_AMOUNT_ETH",
        "SCAN_INTERVAL_SECONDS",
        "ALERT_COOLDOWN_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    args = build_worker_args()
    assert "--discover" in args
    assert args[args.index("--amount-eth") + 1] == "0.1"
    assert args[args.index("--interval") + 1] == "10"
    assert args[args.index("--database") + 1] == "/data/opportunities.db"


def test_worker_accepts_deployment_configuration(monkeypatch) -> None:
    monkeypatch.setenv("FLASH_LOAN_AMOUNT_ETH", "1")
    monkeypatch.setenv("SCAN_INTERVAL_SECONDS", "30")
    monkeypatch.setenv("ALERT_COOLDOWN_SECONDS", "600")
    args = build_worker_args()
    assert args[args.index("--amount-eth") + 1] == "1"
    assert args[args.index("--interval") + 1] == "30"
    assert args[args.index("--cooldown") + 1] == "600"


def test_worker_exposes_no_wallet_signing_or_broadcasting() -> None:
    root = Path(__file__).parents[2]
    sources = (
        (root / "scanner" / "jaytradingbot_scanner" / "worker.py").read_text(),
        (root / "Dockerfile.worker").read_text(),
    )
    combined = "\n".join(sources).lower()
    for forbidden in (
        "private_key",
        "sign_transaction",
        "send_transaction",
        "send_raw_transaction",
        "window.ethereum",
    ):
        assert forbidden not in combined


def test_worker_container_runs_as_non_root() -> None:
    dockerfile = (Path(__file__).parents[2] / "Dockerfile.worker").read_text()
    assert "USER scanner" in dockerfile
    assert 'CMD ["jay-worker"]' in dockerfile
