from jaytradingbot_scanner.discovery import (
    DEFAULT_AMOUNTS_WEI,
    STABLECOINS,
    UNISWAP_V2_ROUTER,
    UNISWAP_V3_FEES,
    UNISWAP_V3_ROUTER,
    SUSHISWAP_V2_ROUTER,
    build_default_cycles,
)
from jaytradingbot_scanner.models import RouterKind


def test_discovery_builds_all_venues_tokens_fees_and_sizes() -> None:
    cycles = build_default_cycles()
    expected_per_amount = len(STABLECOINS) * (len(UNISWAP_V3_FEES) + 2)
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


def test_every_candidate_is_closed_and_uses_two_allowlisted_legs() -> None:
    for cycle in build_default_cycles((10**15,)):
        assert len(cycle.legs) == 2
        assert cycle.legs[0].token_in == cycle.asset
        assert cycle.legs[0].token_out == cycle.legs[1].token_in
        assert cycle.legs[1].token_out == cycle.asset
        assert cycle.amount_in == 10**15


def test_discovery_rejects_non_positive_amounts() -> None:
    for amount in (0, -1):
        try:
            build_default_cycles((amount,))
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
