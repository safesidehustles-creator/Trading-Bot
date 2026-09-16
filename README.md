# JayTradingBot

JayTradingBot is a safety-first Solidity foundation for atomic flash-loan arbitrage using Aave V3 and allowlisted Uniswap-compatible routers.

It **does not** create a token, exploit a protocol, discover profitable trades on-chain, promise returns, or require a 0.1/0.5/1 ETH deposit. A legitimate flash loan borrows and repays within one transaction. The caller still needs native ETH only to pay transaction gas.

## Project status

The contract is intentionally **undeployed**. Development uses unit tests, Ethereum forks, and read-only RPC calls only. The phase-one scanner in [`scanner/`](scanner/) evaluates opportunities without a private key and cannot sign or broadcast transactions.

## Execution flow

1. An off-chain searcher quotes a closed route that starts and ends with the Aave loan asset.
2. The owner calls `startFlashArbitrage` with per-leg minimum outputs, a deadline, and a minimum net profit.
3. Aave sends the asset and calls `executeOperation`.
4. The contract executes only allowlisted tokens, routers, and route types.
5. If the ending balance cannot cover the principal, Aave premium, and minimum profit, the transaction reverts atomically.
6. Aave pulls repayment. The contract then transfers only the realized profit to `profitRecipient`.

## Safety controls

- Owner-only execution and configuration
- Aave pool and callback-initiator authentication
- Token and router allowlists
- Closed-loop route validation
- Per-leg `amountOutMinimum` slippage protection
- Transaction deadline
- Caller-defined minimum net profit
- Emergency pause and owner-only rescue
- Exact token approvals that are cleared after each swap
- Reentrancy guard on the external entry point

These controls reduce risk; they do not make arbitrage profitable or eliminate smart-contract, oracle, MEV, liquidity, gas, and integration risks. This code has not been audited. Do not deploy with real funds before independent review and mainnet-fork testing.

## Build and test

Install [Foundry](https://book.getfoundry.sh/getting-started/installation), then run:

```bash
forge fmt --check
forge build
forge test -vvv
```

For realistic validation, add mainnet-fork integration tests at a fixed block and source deployment addresses from the official Aave and Uniswap registries. Never copy addresses from unsolicited tutorials.

## Route encoding

Each `SwapLeg` includes a router kind, router, input/output tokens, minimum output, and `route` bytes.

- V2-compatible route: `abi.encode(address[] path)`
- V3-compatible route: Uniswap packed path (`token + fee + token [+ fee + token...]`)

The first leg must begin with the loan asset, every leg must connect to the next, and the final leg must return to the loan asset.

## Deployment checklist

1. Confirm official Aave V3 `PoolAddressesProvider` for the target chain.
2. Deploy with the provider and a secure owner address (preferably a multisig).
3. Allow only the exact ERC-20 tokens and router contracts required.
4. Build an off-chain quoter/searcher that includes Aave premium, gas, price impact, and conservative slippage.
5. Simulate the exact signed transaction against a current mainnet fork.
6. Start with dry runs. Obtain an independent audit before production use.

## Legal and ethical use

Use only ordinary, authorized market arbitrage. Do not use this project to exploit protocol vulnerabilities, manipulate markets, mislead depositors, accept pooled customer funds, or advertise guaranteed returns.
