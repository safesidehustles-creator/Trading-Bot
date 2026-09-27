from __future__ import annotations

from collections.abc import Iterable

from .models import Cycle, Leg, RouterKind

WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
STABLECOINS = {
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
}
UNISWAP_V3_QUOTER_V2 = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
UNISWAP_V3_ROUTER = "0xE592427A0AEce92De3Edee1F18E0157C05861564"
UNISWAP_V2_ROUTER = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
SUSHISWAP_V2_ROUTER = "0xd9e1cE17f2641F24aE83637ab66a2cca9C378B9F"
UNISWAP_V3_FEES = (100, 500, 3000, 10_000)
DEFAULT_AMOUNTS_WEI = (10**15, 10**16, 10**17, 10**18)


def _v3_cycle(symbol: str, token: str, fee: int, amount: int) -> Cycle:
    label = f"Uniswap V3 {fee / 1_000_000:.2%}"
    return Cycle(
        name=f"WETH-{symbol}-WETH · {label} · {amount} wei",
        asset=WETH,
        amount_in=amount,
        legs=(
            Leg(
                RouterKind.V3,
                UNISWAP_V3_QUOTER_V2,
                UNISWAP_V3_ROUTER,
                WETH,
                token,
                fee,
            ),
            Leg(
                RouterKind.V3,
                UNISWAP_V3_QUOTER_V2,
                UNISWAP_V3_ROUTER,
                token,
                WETH,
                fee,
            ),
        ),
    )


def _v2_cycle(
    symbol: str,
    token: str,
    venue: str,
    router: str,
    amount: int,
) -> Cycle:
    return Cycle(
        name=f"WETH-{symbol}-WETH · {venue} · {amount} wei",
        asset=WETH,
        amount_in=amount,
        legs=(
            Leg(RouterKind.V2, router, router, WETH, token),
            Leg(RouterKind.V2, router, router, token, WETH),
        ),
    )


def build_default_cycles(
    amounts: Iterable[int] = DEFAULT_AMOUNTS_WEI,
) -> tuple[Cycle, ...]:
    """Build allowlisted quote candidates; no account or execution capability."""
    cycles: list[Cycle] = []
    for amount in amounts:
        if amount <= 0:
            raise ValueError("discovery amounts must be positive")
        for symbol, token in STABLECOINS.items():
            cycles.extend(
                _v3_cycle(symbol, token, fee, amount)
                for fee in UNISWAP_V3_FEES
            )
            cycles.append(
                _v2_cycle(symbol, token, "Uniswap V2", UNISWAP_V2_ROUTER, amount)
            )
            cycles.append(
                _v2_cycle(symbol, token, "SushiSwap V2", SUSHISWAP_V2_ROUTER, amount)
            )
    return tuple(cycles)
