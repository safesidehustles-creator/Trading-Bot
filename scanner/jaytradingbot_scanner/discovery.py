from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

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


@dataclass(frozen=True)
class Market:
    name: str
    kind: RouterKind
    quoter: str
    router: str
    fee: int | None = None


MARKETS = (
    *(
        Market(
            f"Uniswap V3 {fee / 1_000_000:.2%}",
            RouterKind.V3,
            UNISWAP_V3_QUOTER_V2,
            UNISWAP_V3_ROUTER,
            fee,
        )
        for fee in UNISWAP_V3_FEES
    ),
    Market("Uniswap V2", RouterKind.V2, UNISWAP_V2_ROUTER, UNISWAP_V2_ROUTER),
    Market("SushiSwap V2", RouterKind.V2, SUSHISWAP_V2_ROUTER, SUSHISWAP_V2_ROUTER),
)


def _leg(market: Market, token_in: str, token_out: str) -> Leg:
    return Leg(
        market.kind,
        market.quoter,
        market.router,
        token_in,
        token_out,
        market.fee,
    )


def _cross_market_cycle(
    symbol: str,
    token: str,
    buy_market: Market,
    sell_market: Market,
    amount: int,
) -> Cycle:
    return Cycle(
        name=(
            f"WETH-{symbol}-WETH · {buy_market.name} → "
            f"{sell_market.name} · {amount} wei"
        ),
        asset=WETH,
        amount_in=amount,
        legs=(
            _leg(buy_market, WETH, token),
            _leg(sell_market, token, WETH),
        ),
    )


def _validate_amounts(amounts: Iterable[int]) -> tuple[int, ...]:
    values = tuple(amounts)
    if any(amount <= 0 for amount in values):
        raise ValueError("discovery amounts must be positive")
    return values


def build_default_cycles(
    amounts: Iterable[int] = DEFAULT_AMOUNTS_WEI,
) -> tuple[Cycle, ...]:
    """Build every directed cross-market pair from the allowlisted catalog."""
    cycles: list[Cycle] = []
    for amount in _validate_amounts(amounts):
        for symbol, token in STABLECOINS.items():
            for buy_market in MARKETS:
                for sell_market in MARKETS:
                    if buy_market == sell_market:
                        continue
                    cycles.append(
                        _cross_market_cycle(
                            symbol, token, buy_market, sell_market, amount
                        )
                    )
    return tuple(cycles)


def build_web_cycles(amount: int) -> tuple[Cycle, ...]:
    """Prioritize 36 cross-market candidates for one hosted read-only scan."""
    _validate_amounts((amount,))
    sushi = next(market for market in MARKETS if market.name == "SushiSwap V2")
    uniswap_v2 = next(market for market in MARKETS if market.name == "Uniswap V2")
    uniswap_v3_005 = next(
        market for market in MARKETS if market.fee == 500
    )
    pairs = [
        (left, right)
        for left in MARKETS
        for right in MARKETS
        if left != right and (left == sushi or right == sushi)
    ]
    pairs.extend(((uniswap_v2, uniswap_v3_005), (uniswap_v3_005, uniswap_v2)))

    cycles: list[Cycle] = []
    for symbol, token in STABLECOINS.items():
        cycles.extend(
            _cross_market_cycle(symbol, token, buy, sell, amount)
            for buy, sell in pairs
        )
    return tuple(cycles)
