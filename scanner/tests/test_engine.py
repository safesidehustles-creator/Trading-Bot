from jaytradingbot_scanner.engine import OpportunityEngine
from jaytradingbot_scanner.models import Cycle, Leg, RouterKind, ScanPolicy

WETH = "0x0000000000000000000000000000000000000001"
USDC = "0x0000000000000000000000000000000000000002"


def cycle() -> Cycle:
    return Cycle(
        name="test",
        asset=WETH,
        amount_in=1_000_000,
        legs=(
            Leg(RouterKind.V2, "q1", "r1", WETH, USDC),
            Leg(RouterKind.V2, "q2", "r2", USDC, WETH),
        ),
    )


def test_accepts_profit_after_premium_gas_slippage_and_margin() -> None:
    outputs = iter((1_200_000, 1_100_000))
    engine = OpportunityEngine(lambda _leg, _amount: next(outputs))
    result = engine.evaluate(
        cycle(),
        ScanPolicy(gas_units=100, minimum_profit=10_000, safety_margin_bps=20, slippage_bps=30),
        premium_bps=5,
        gas_price_wei=10,
    )
    assert result.executable is True
    assert result.net_profit == 95_200


def test_rejects_route_below_required_profit() -> None:
    outputs = iter((1_010_000, 1_005_000))
    result = OpportunityEngine(lambda _leg, _amount: next(outputs)).evaluate(
        cycle(),
        ScanPolicy(gas_units=100, minimum_profit=10_000, safety_margin_bps=20, slippage_bps=30),
        premium_bps=5,
        gas_price_wei=10,
    )
    assert result.executable is False
    assert result.rejection_reason is not None


def test_rejects_non_closed_route() -> None:
    broken = Cycle(
        name="broken",
        asset=WETH,
        amount_in=1,
        legs=(
            Leg(RouterKind.V2, "q1", "r1", WETH, USDC),
            Leg(RouterKind.V2, "q2", "r2", WETH, USDC),
        ),
    )
    try:
        OpportunityEngine(lambda _leg, amount: amount).evaluate(
            broken, ScanPolicy(1, 1), 5, 1
        )
    except ValueError as exc:
        assert "continuous" in str(exc)
    else:
        raise AssertionError("broken route was accepted")
