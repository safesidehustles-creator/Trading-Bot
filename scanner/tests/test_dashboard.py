from datetime import UTC, datetime

from jaytradingbot_scanner.dashboard import DashboardData
from jaytradingbot_scanner.models import QuoteResult
from jaytradingbot_scanner.monitor import OpportunityStore


def _result(cycle: str, executable: bool, profit: int) -> QuoteResult:
    return QuoteResult(
        cycle=cycle,
        amount_in=1_000,
        quoted_amount_out=1_100,
        protected_amount_out=1_090,
        flash_loan_premium=5,
        gas_cost=10,
        safety_margin=1,
        net_profit=profit,
        executable=executable,
        rejection_reason=None if executable else "below threshold",
        leg_quotes=(1_050, 1_100),
        leg_minimums=(1_040, 1_090),
    )


def _database(tmp_path):
    path = tmp_path / "opportunities.db"
    store = OpportunityStore(str(path))
    now = datetime(2026, 9, 16, tzinfo=UTC)
    store.record_result(_result("route-a", True, 75), now)
    store.record_result(_result("route-a", False, -12), now)
    store.record_result(_result("route-b", False, -20), now)
    store.record_error("route-b", "RPC unavailable", now)
    store.mark_alerted("route-a", 1_000)
    store.close()
    return path


def test_summary_is_read_only_and_counts_statuses(tmp_path) -> None:
    dashboard = DashboardData(str(_database(tmp_path)))
    summary = dashboard.summary()
    assert summary == {
        "total_scans": 4,
        "opportunities": 1,
        "errors": 1,
        "last_scan": "2026-09-16T00:00:00+00:00",
        "routes_alerted": 1,
        "mode": "read-only",
        "execution_enabled": False,
    }
    dashboard.close()


def test_recent_result_filters_and_limit_cap(tmp_path) -> None:
    dashboard = DashboardData(str(_database(tmp_path)))
    assert len(dashboard.recent_results(status="opportunity")) == 1
    assert len(dashboard.recent_results(status="rejected")) == 2
    assert len(dashboard.recent_results(status="error")) == 1
    try:
        dashboard.recent_results(status="invalid")
    except ValueError as exc:
        assert "status must be" in str(exc)
    else:
        raise AssertionError("invalid filter was accepted")
    dashboard.close()


def test_route_health_uses_integer_safe_profit_comparison(tmp_path) -> None:
    dashboard = DashboardData(str(_database(tmp_path)))
    routes = {item["cycle"]: item for item in dashboard.route_health()}
    assert routes["route-a"]["scans"] == 2
    assert routes["route-a"]["opportunities"] == 1
    assert routes["route-a"]["best_net_profit"] == "75"
    assert routes["route-b"]["errors"] == 1
    assert routes["route-b"]["last_status"] == "error"
    dashboard.close()


def test_missing_database_has_clear_instruction(tmp_path) -> None:
    try:
        DashboardData(str(tmp_path / "missing.db"))
    except FileNotFoundError as exc:
        assert "run jay-monitor --once first" in str(exc)
    else:
        raise AssertionError("missing database was accepted")
