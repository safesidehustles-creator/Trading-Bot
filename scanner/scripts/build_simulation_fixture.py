"""Print deterministic simulation-only calldata for the mainnet-fork safety test."""

import json

from jaytradingbot_scanner.calldata import build_unsigned_call
from jaytradingbot_scanner.models import Cycle, Leg, QuoteResult, RouterKind

WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"

cycle = Cycle(
    name="mainnet-fork rejection fixture",
    asset=WETH,
    amount_in=10**18,
    legs=(
        Leg(RouterKind.V3, ROUTER, ROUTER, WETH, USDC, 500),
        Leg(RouterKind.V3, ROUTER, ROUTER, USDC, WETH, 500),
    ),
)
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
    cycle,
    result,
    contract_address="0x00000000000000000000000000000000000000B0",
    profit_recipient="0x000000000000000000000000000000000000dEaD",
    minimum_profit=0,
    deadline=2**256 - 1,
    simulation_only=True,
)
print(json.dumps(call.to_dict(), indent=2))
