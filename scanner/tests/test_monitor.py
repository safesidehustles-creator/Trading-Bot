from jaytradingbot_scanner.models import Cycle, Leg, RouterKind, ScanPolicy
from jaytradingbot_scanner.monitor import MonitorService, OpportunityStore

WETH = "0x0000000000000000000000000000000000000001"
USDC = "0x0000000000000000000000000000000000000002"


class FakeChain:
    gas_price_wei = 1

    def __init__(self, outputs: list[int]) -> None:
        self.outputs = iter(outputs)

    def aave_premium_bps(self, _provider: str) -> int:
        return 5

    def quote_leg(self, _leg: object, _amount: int) -> int:
        return next(self.outputs)


class CollectingSink:
    def __init__(self) -> None:
        self.results = []

    def send(self, result: object) -> None:
        self.results.append(result)


def _cycle(name: str = "cycle") -> Cycle:
    return Cycle(
        name=name,
        asset=WETH,
        amount_in=1_000_000,
        legs=(
            Leg(RouterKind.V2, "q1", "r1", WETH, USDC),
            Leg(RouterKind.V2, "q2", "r2", USDC, WETH),
        ),
    )


def test_records_and_alerts_profitable_result_once_during_cooldown(tmp_path) -> None:
    database = tmp_path / "monitor.db"
    store = OpportunityStore(str(database))
    sink = CollectingSink()
    policy = ScanPolicy(gas_units=1, minimum_profit=1, safety_margin_bps=0, slippage_bps=0)

    first = MonitorService(
        FakeChain([1_100_000, 1_050_000]), "provider", policy, [_cycle()], store, [sink], 300
    )
    first.run_once(now_epoch=1_000)
    second = MonitorService(
        FakeChain([1_100_000, 1_050_000]), "provider", policy, [_cycle()], store, [sink], 300
    )
    second.run_once(now_epoch=1_100)

    assert len(sink.results) == 1
    count = store.connection.execute("SELECT COUNT(*) FROM scan_results").fetchone()[0]
    assert count == 2
    store.close()


def test_rejected_result_is_recorded_but_not_alerted(tmp_path) -> None:
    store = OpportunityStore(str(tmp_path / "monitor.db"))
    sink = CollectingSink()
    service = MonitorService(
        FakeChain([1_000_000, 999_000]),
        "provider",
        ScanPolicy(gas_units=1, minimum_profit=1),
        [_cycle()],
        store,
        [sink],
    )
    results = service.run_once(now_epoch=1_000)
    assert results[0].executable is False
    assert sink.results == []
    stored = store.connection.execute(
        "SELECT executable, error FROM scan_results"
    ).fetchone()
    assert stored == (0, None)
    store.close()


def test_quote_error_does_not_stop_other_cycles(tmp_path) -> None:
    store = OpportunityStore(str(tmp_path / "monitor.db"))

    class MixedChain(FakeChain):
        calls = 0

        def quote_leg(self, _leg: object, amount: int) -> int:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary RPC error")
            return amount + 100_000

    service = MonitorService(
        MixedChain([]),
        "provider",
        ScanPolicy(gas_units=1, minimum_profit=1, safety_margin_bps=0, slippage_bps=0),
        [_cycle("broken"), _cycle("healthy")],
        store,
        [],
    )
    results = service.run_once(now_epoch=1_000)
    assert [result.cycle for result in results] == ["healthy"]
    error = store.connection.execute(
        "SELECT error FROM scan_results WHERE cycle = 'broken'"
    ).fetchone()[0]
    assert "temporary RPC error" in error
    store.close()


def test_schema_uses_text_for_large_integer_values(tmp_path) -> None:
    store = OpportunityStore(str(tmp_path / "monitor.db"))
    columns = {
        row[1]: row[2]
        for row in store.connection.execute("PRAGMA table_info(scan_results)").fetchall()
    }
    assert columns["net_profit"] == "TEXT"
    assert columns["gas_cost"] == "TEXT"
    store.close()
