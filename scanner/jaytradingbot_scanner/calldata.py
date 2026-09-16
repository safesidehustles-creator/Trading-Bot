from __future__ import annotations

from dataclasses import asdict, dataclass

from eth_abi import encode
from web3 import Web3

from .models import Cycle, QuoteResult, RouterKind

START_ABI = [{
    "inputs": [
        {"internalType": "address", "name": "asset", "type": "address"},
        {"internalType": "uint256", "name": "amount", "type": "uint256"},
        {
            "components": [
                {"internalType": "uint8", "name": "kind", "type": "uint8"},
                {"internalType": "address", "name": "router", "type": "address"},
                {"internalType": "address", "name": "tokenIn", "type": "address"},
                {"internalType": "address", "name": "tokenOut", "type": "address"},
                {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                {"internalType": "bytes", "name": "route", "type": "bytes"},
            ],
            "internalType": "struct JayTradingBotFlashArbitrage.SwapLeg[]",
            "name": "legs",
            "type": "tuple[]",
        },
        {"internalType": "uint256", "name": "minimumProfit", "type": "uint256"},
        {"internalType": "uint256", "name": "deadline", "type": "uint256"},
        {"internalType": "address", "name": "profitRecipient", "type": "address"},
    ],
    "name": "startFlashArbitrage",
    "outputs": [{"internalType": "uint256", "name": "profit", "type": "uint256"}],
    "stateMutability": "nonpayable",
    "type": "function",
}]


@dataclass(frozen=True)
class UnsignedCall:
    cycle: str
    chain_id: int
    to: str
    value: int
    data: str
    deadline: int
    simulation_only: bool
    signed: bool = False
    broadcast: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_unsigned_call(
    cycle: Cycle,
    result: QuoteResult,
    contract_address: str,
    profit_recipient: str,
    minimum_profit: int,
    deadline: int,
    chain_id: int = 1,
    *,
    simulation_only: bool = False,
) -> UnsignedCall:
    if not result.executable and not simulation_only:
        raise ValueError("refusing calldata for a rejected opportunity")
    if result.cycle != cycle.name or len(result.leg_minimums) != len(cycle.legs):
        raise ValueError("quote result does not match cycle")
    if deadline <= 0 or minimum_profit < 0:
        raise ValueError("invalid deadline or minimum profit")

    legs: list[tuple[int, str, str, str, int, bytes]] = []
    for leg, amount_out_minimum in zip(cycle.legs, result.leg_minimums, strict=True):
        if leg.kind == RouterKind.V2:
            route = encode(
                ["address[]"],
                [[Web3.to_checksum_address(leg.token_in), Web3.to_checksum_address(leg.token_out)]],
            )
            kind = 0
        else:
            if leg.fee is None or not 0 <= leg.fee < 2**24:
                raise ValueError("V3 leg requires a valid uint24 fee")
            route = (
                bytes.fromhex(leg.token_in.removeprefix("0x"))
                + leg.fee.to_bytes(3, "big")
                + bytes.fromhex(leg.token_out.removeprefix("0x"))
            )
            kind = 1
        legs.append((
            kind,
            Web3.to_checksum_address(leg.router),
            Web3.to_checksum_address(leg.token_in),
            Web3.to_checksum_address(leg.token_out),
            amount_out_minimum,
            route,
        ))

    contract = Web3().eth.contract(abi=START_ABI)
    data = contract.encode_abi(
        "startFlashArbitrage",
        args=[
            Web3.to_checksum_address(cycle.asset),
            cycle.amount_in,
            legs,
            minimum_profit,
            deadline,
            Web3.to_checksum_address(profit_recipient),
        ],
    )
    return UnsignedCall(
        cycle=cycle.name,
        chain_id=chain_id,
        to=Web3.to_checksum_address(contract_address),
        value=0,
        data=data,
        deadline=deadline,
        simulation_only=simulation_only,
    )
