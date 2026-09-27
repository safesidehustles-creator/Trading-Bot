from jaytradingbot_scanner.discovery import (
    DEFAULT_AMOUNTS_WEI,
    MARKETS,
    STABLECOINS,
    UNISWAP_V2_ROUTER,
    UNISWAP_V3_FEES,
    UNISWAP_V3_ROUTER,
    SUSHISWAP_V2_ROUTER,
    build_default_cycles,
    build_web_cycles,
)
from jaytradingbot_scanner.models import RouterKind


def test_discovery_builds_cross_market_routes_for_all_sizes() -> None:
    cycles = build_default_cycles()
    expected_per_amount = len(STABLECOINS) * len(MARKETS) * (len(MARKETS) - 1)
    assert len(cycles) == len(DEFAULT_AMOUNTS_WEI) * expected_per_amount
    assert {cycle.amount_in for cycle in cycles} == set(DEFAULT_AMOUNTS_WEI)
    assert len({cycle.name for cycle in cycles}) == len(cycles)

    routers = {leg.router for cycle in cycles for leg in cycle.legs}
    assert routers == {
        UNISWAP_V3_ROUTER,
        UNISWAP_V2_ROUTER,
        SUSHISWAP_V2_ROUTER,
    }
    fees = {
        leg.fee
        for cycle in cycles
        for leg in cycle.legs
        if leg.kind == RouterKind.V3
    }
    assert fees == set(UNISWAP_V3_FEES)


def test_every_candidate_is_closed_and_cross_market() -> None:
    for cycle in build_default_cycles((10**15,)):
        assert len(cycle.legs) == 2
        assert cycle.legs[0].token_in == cycle.asset
        assert cycle.legs[0].token_out == cycle.legs[1].token_in
        assert cycle.legs[1].token_out == cycle.asset
        assert cycle.amount_in == 10**15
        first = (cycle.legs[0].router, cycle.legs[0].fee)
        second = (cycle.legs[1].router, cycle.legs[1].fee)
        assert first != second


def test_hosted_subset_is_bounded_and_cross_market() -> None:
    cycles = build_web_cycles(10**15)
    assert len(cycles) == 36
    assert {cycle.amount_in for cycle in cycles} == {10**15}
    assert {cycle.legs[0].token_out for cycle in cycles} == set(STABLECOINS.values())
    for cycle in cycles:
        first = (cycle.legs[0].router, cycle.legs[0].fee)
        second = (cycle.legs[1].router, cycle.legs[1].fee)
        assert first != second


def test_discovery_rejects_non_positive_amounts() -> None:
    for amount in (0, -1):
        for builder in (
            lambda: build_default_cycles((amount,)),
            lambda: build_web_cycles(amount),
        ):
            try:
                builder()
            except ValueError as exc:
                assert "positive" in str(exc)
            else:
                raise AssertionError("invalid discovery amount was accepted")


def test_discovery_has_no_execution_capability() -> None:
    public_names = {
        name.lower()
        for name in dir(__import__(
            "jaytradingbot_scanner.discovery",
            fromlist=["*"],
        ))
    }
    forbidden = {
        "private_key",
        "sign_transaction",
        "send_transaction",
        "send_raw_transaction",
        "broadcast",
    }
    assert public_names.isdisjoint(forbidden)
