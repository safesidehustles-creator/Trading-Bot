from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RouterKind(StrEnum):
    V2 = "v2"
    V3 = "v3"


@dataclass(frozen=True)
class Leg:
    kind: RouterKind
    quoter: str
    router: str
    token_in: str
    token_out: str
    fee: int | None = None


@dataclass(frozen=True)
class Cycle:
    name: str
    asset: str
    amount_in: int
    legs: tuple[Leg, ...]


@dataclass(frozen=True)
class ScanPolicy:
    gas_units: int
    minimum_profit: int
    safety_margin_bps: int = 20
    slippage_bps: int = 30


@dataclass(frozen=True)
class QuoteResult:
    cycle: str
    amount_in: int
    quoted_amount_out: int
    protected_amount_out: int
    flash_loan_premium: int
    gas_cost: int
    safety_margin: int
    net_profit: int
    executable: bool
    rejection_reason: str | None
