import json
from pathlib import Path

from web3 import Web3

from jaytradingbot_scanner.calldata import START_ABI, build_unsigned_call
from jaytradingbot_scanner.models import Cycle, Leg, QuoteResult, RouterKind

WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
BOT = "0x00000000000000000000000000000000000000B0"
RECIPIENT = "0x000000000000000000000000000000000000dEaD"
SMALL_FLASH_LOAN_AMOUNT = 10**15  # 0.001 WETH


def _cycle() -> Cycle:
    return Cycle(
        name="fixture",
        asset=WETH,
        amount_in=SMALL_FLASH_LOAN_AMOUNT,
        legs=(
            Leg(RouterKind.V3, ROUTER, ROUTER, WETH, USDC, 500),
            Leg(RouterKind.V3, ROUTER, ROUTER, USDC, WETH, 500),
        ),
    )


def _result(executable: bool) -> QuoteResult:
    return QuoteResult(
        cycle="fixture",
        amount_in=SMALL_FLASH_LOAN_AMOUNT,
        quoted_amount_out=999_000_000_000_000,
        protected_amount_out=995_000_000_000_000,
        flash_loan_premium=500_000_000_000,
        gas_cost=1,
        safety_margin=1,
        net_profit=-5_500_000_000_001,
        executable=executable,
        rejection_reason=None if executable else "not profitable",
        leg_quotes=(3_000_000, 999_000_000_000_000),
        leg_minimums=(0, 0),
    )


def test_builds_decodable_unsigned_call() -> None:
    call = build_unsigned_call(
        _cycle(), _result(True), BOT, RECIPIENT, 0, 2**256 - 1
    )
    assert call.signed is False
    assert call.broadcast is False
    assert call.value == 0
    contract = Web3().eth.contract(abi=START_ABI)
    function, arguments = contract.decode_function_input(call.data)
    assert function.fn_name == "startFlashArbitrage"
    assert arguments["asset"] == Web3.to_checksum_address(WETH)
    assert arguments["amount"] == SMALL_FLASH_LOAN_AMOUNT
    assert len(arguments["legs"]) == 2


def test_refuses_rejected_opportunity() -> None:
    try:
        build_unsigned_call(_cycle(), _result(False), BOT, RECIPIENT, 0, 1)
    except ValueError as exc:
        assert "rejected opportunity" in str(exc)
    else:
        raise AssertionError("rejected opportunity produced calldata")


def test_allows_rejected_route_only_when_marked_simulation() -> None:
    call = build_unsigned_call(
        _cycle(), _result(False), BOT, RECIPIENT, 0, 2**256 - 1, simulation_only=True
    )
    assert call.simulation_only is True
    assert call.signed is False
    assert call.broadcast is False


def test_committed_fork_fixture_matches_generator() -> None:
    cycle = _cycle()
    cycle = Cycle(
        name="mainnet-fork rejection fixture",
        asset=cycle.asset,
        amount_in=cycle.amount_in,
        legs=cycle.legs,
    )
    result = _result(False)
    result = QuoteResult(
        cycle=cycle.name,
        amount_in=cycle.amount_in,
        quoted_amount_out=0,
        protected_amount_out=0,
        flash_loan_premium=0,
        gas_cost=0,
        safety_margin=0,
        net_profit=-1,
        executable=False,
        rejection_reason="simulation-only known fee-losing route",
        leg_quotes=(0, 0),
        leg_minimums=(0, 0),
    )
    call = build_unsigned_call(
        cycle, result, BOT, RECIPIENT, 0, 2**256 - 1, simulation_only=True
    )
    fixture_path = Path(__file__).parents[1] / "fixtures" / "mainnet_rejection_call.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert fixture["data"] == call.data
    assert fixture["signed"] is False
    assert fixture["broadcast"] is False

    contract = Web3().eth.contract(abi=START_ABI)
    _, arguments = contract.decode_function_input(fixture["data"])
    assert arguments["amount"] == SMALL_FLASH_LOAN_AMOUNT
