// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {JayTradingBotFlashArbitrage} from "../src/JayTradingBotFlashArbitrage.sol";

interface Vm {
    function createSelectFork(string calldata urlOrAlias) external returns (uint256 forkId);
    function createSelectFork(string calldata urlOrAlias, uint256 blockNumber)
        external
        returns (uint256 forkId);
    function envOr(string calldata name, string calldata defaultValue)
        external
        returns (string memory value);
    function envOr(string calldata name, uint256 defaultValue) external returns (uint256 value);
    function expectRevert(bytes4 revertData) external;
}

/// @dev Live-state integration test using actual Ethereum Aave V3 and Uniswap V3 contracts.
contract MainnetForkTest {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    address private constant AAVE_V3_PROVIDER = 0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e;
    address private constant UNISWAP_V3_ROUTER = 0xE592427A0AEce92De3Edee1F18E0157C05861564;
    address private constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address private constant USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;

    JayTradingBotFlashArbitrage private bot;
    bool private forkEnabled;

    function setUp() public {
        string memory rpcUrl = vm.envOr("ETHEREUM_RPC_URL", string(""));
        if (bytes(rpcUrl).length == 0) return;

        uint256 forkBlock = vm.envOr("FORK_BLOCK_NUMBER", uint256(0));
        if (forkBlock == 0) {
            vm.createSelectFork(rpcUrl);
        } else {
            vm.createSelectFork(rpcUrl, forkBlock);
        }
        forkEnabled = true;
        bot = new JayTradingBotFlashArbitrage(AAVE_V3_PROVIDER, address(this));
        bot.setTokenAllowed(WETH, true);
        bot.setTokenAllowed(USDC, true);
        bot.setRouterAllowed(UNISWAP_V3_ROUTER, true);
    }

    /// @notice Real Aave loan + real Uniswap round trip must revert because fees make it unprofitable.
    /// @dev Expecting our exact custom error proves execution reached the bot's profit guard.
    function testForkRejectsRealUnprofitableAaveUniswapRoute() public {
        if (!forkEnabled) return;

        JayTradingBotFlashArbitrage.SwapLeg[] memory legs =
            new JayTradingBotFlashArbitrage.SwapLeg[](2);

        legs[0] = JayTradingBotFlashArbitrage.SwapLeg({
            kind: JayTradingBotFlashArbitrage.RouterKind.UniswapV3Compatible,
            router: UNISWAP_V3_ROUTER,
            tokenIn: WETH,
            tokenOut: USDC,
            amountOutMinimum: 0,
            route: abi.encodePacked(WETH, uint24(500), USDC)
        });
        legs[1] = JayTradingBotFlashArbitrage.SwapLeg({
            kind: JayTradingBotFlashArbitrage.RouterKind.UniswapV3Compatible,
            router: UNISWAP_V3_ROUTER,
            tokenIn: USDC,
            tokenOut: WETH,
            amountOutMinimum: 0,
            route: abi.encodePacked(USDC, uint24(500), WETH)
        });

        vm.expectRevert(JayTradingBotFlashArbitrage.InsufficientProfit.selector);
        bot.startFlashArbitrage(WETH, 1 ether, legs, 0, block.timestamp + 60, address(this));
    }
}
