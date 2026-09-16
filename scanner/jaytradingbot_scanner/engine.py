from __future__ import annotations

from collections.abc import Callable

from .models import Cycle, QuoteResult, ScanPolicy

QuoteFunction = Callable[[object, int], int]


class OpportunityEngine:
    """Pure evaluator. It cannot sign or broadcast transactions."""

    def __init__(self, quote_leg: QuoteFunction) -> None:
        self._quote_leg = quote_leg

    def evaluate(
        self,
        cycle: Cycle,
        policy: ScanPolicy,
        premium_bps: int,
        gas_price_wei: int,
    ) -> QuoteResult:
        self._validate_cycle(cycle)
        if not 0 <= policy.slippage_bps < 10_000:
            raise ValueError("slippage_bps must be between 0 and 9999")
        if not 0 <= policy.safety_margin_bps < 10_000:
            raise ValueError("safety_margin_bps must be between 0 and 9999")

        quoted = cycle.amount_in
        for leg in cycle.legs:
            quoted = self._quote_leg(leg, quoted)
            if quoted <= 0:
                raise ValueError("quoter returned a non-positive amount")

        protected = quoted * (10_000 - policy.slippage_bps) // 10_000
        premium = cycle.amount_in * premium_bps // 10_000
        gas_cost = policy.gas_units * gas_price_wei
        safety_margin = cycle.amount_in * policy.safety_margin_bps // 10_000
        net_profit = protected - cycle.amount_in - premium - gas_cost
        required = policy.minimum_profit + safety_margin
        executable = net_profit >= required
        reason = None if executable else (
            f"net profit {net_profit} is below required {required}"
        )

        return QuoteResult(
            cycle=cycle.name,
            amount_in=cycle.amount_in,
            quoted_amount_out=quoted,
            protected_amount_out=protected,
            flash_loan_premium=premium,
            gas_cost=gas_cost,
            safety_margin=safety_margin,
            net_profit=net_profit,
            executable=executable,
            rejection_reason=reason,
        )

    @staticmethod
    def _validate_cycle(cycle: Cycle) -> None:
        if cycle.amount_in <= 0 or len(cycle.legs) < 2:
            raise ValueError("cycle requires a positive amount and at least two legs")
        expected = cycle.asset.lower()
        for leg in cycle.legs:
            if leg.token_in.lower() != expected:
                raise ValueError("route legs are not continuous")
            if leg.token_in.lower() == leg.token_out.lower():
                raise ValueError("a leg cannot swap a token into itself")
            expected = leg.token_out.lower()
        if expected != cycle.asset.lower():
            raise ValueError("cycle must finish in the borrowed asset")
