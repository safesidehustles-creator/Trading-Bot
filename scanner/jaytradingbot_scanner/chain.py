from __future__ import annotations

from typing import Any

from web3 import Web3

from .models import Leg, RouterKind

V2_ABI: list[dict[str, Any]] = [{
    "inputs": [
        {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
        {"internalType": "address[]", "name": "path", "type": "address[]"},
    ],
    "name": "getAmountsOut",
    "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
    "stateMutability": "view",
    "type": "function",
}]

V3_QUOTER_V2_ABI: list[dict[str, Any]] = [{
    "inputs": [{
        "components": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
        ],
        "internalType": "struct IQuoterV2.QuoteExactInputSingleParams",
        "name": "params",
        "type": "tuple",
    }],
    "name": "quoteExactInputSingle",
    "outputs": [
        {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
        {"internalType": "uint160", "name": "sqrtPriceX96After", "type": "uint160"},
        {"internalType": "uint32", "name": "initializedTicksCrossed", "type": "uint32"},
        {"internalType": "uint256", "name": "gasEstimate", "type": "uint256"},
    ],
    "stateMutability": "nonpayable",
    "type": "function",
}]

PROVIDER_ABI: list[dict[str, Any]] = [{
    "inputs": [],
    "name": "getPool",
    "outputs": [{"internalType": "address", "name": "", "type": "address"}],
    "stateMutability": "view",
    "type": "function",
}]

POOL_ABI: list[dict[str, Any]] = [{
    "inputs": [],
    "name": "FLASHLOAN_PREMIUM_TOTAL",
    "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
    "stateMutability": "view",
    "type": "function",
}]


class ReadOnlyChain:
    """Ethereum reader with no account, private key, or send method."""

    def __init__(self, rpc_url: str) -> None:
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
        if not self.w3.is_connected():
            raise ConnectionError("could not connect to Ethereum RPC")

    @property
    def gas_price_wei(self) -> int:
        return int(self.w3.eth.gas_price)

    def aave_premium_bps(self, provider: str) -> int:
        registry = self.w3.eth.contract(
            address=Web3.to_checksum_address(provider), abi=PROVIDER_ABI
        )
        pool_address = registry.functions.getPool().call()
        pool = self.w3.eth.contract(address=pool_address, abi=POOL_ABI)
        return int(pool.functions.FLASHLOAN_PREMIUM_TOTAL().call())

    def quote_leg(self, leg: Leg, amount_in: int) -> int:
        token_in = Web3.to_checksum_address(leg.token_in)
        token_out = Web3.to_checksum_address(leg.token_out)
        quoter = Web3.to_checksum_address(leg.quoter)

        if leg.kind == RouterKind.V2:
            contract = self.w3.eth.contract(address=quoter, abi=V2_ABI)
            amounts = contract.functions.getAmountsOut(
                amount_in, [token_in, token_out]
            ).call()
            return int(amounts[-1])

        if leg.fee is None:
            raise ValueError("V3 leg requires a fee tier")
        contract = self.w3.eth.contract(address=quoter, abi=V3_QUOTER_V2_ABI)
        result = contract.functions.quoteExactInputSingle(
            (token_in, token_out, amount_in, leg.fee, 0)
        ).call()
        return int(result[0])
