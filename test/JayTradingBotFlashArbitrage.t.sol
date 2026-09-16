// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {JayTradingBotFlashArbitrage, IERC20, IFlashLoanSimpleReceiver} from
    "../src/JayTradingBotFlashArbitrage.sol";

contract MockToken is IERC20 {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external { balanceOf[to] += amount; }

    function transfer(address to, uint256 amount) external returns (bool) {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 approved = allowance[from][msg.sender];
        if (approved != type(uint256).max) allowance[from][msg.sender] = approved - amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

contract MockProvider {
    address public pool;
    function setPool(address value) external { pool = value; }
    function getPool() external view returns (address) { return pool; }
}

contract MockPool {
    uint256 public constant PREMIUM_BPS = 9;

    function flashLoanSimple(
        address receiver,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16
    ) external {
        MockToken(asset).transfer(receiver, amount);
        uint256 premium = amount * PREMIUM_BPS / 10_000;
        bool ok = IFlashLoanSimpleReceiver(receiver).executeOperation(
            asset, amount, premium, receiver, params
        );
        require(ok, "callback failed");
        MockToken(asset).transferFrom(receiver, address(this), amount + premium);
    }
}

contract MockV2Router {
    uint256 public numerator;
    uint256 public denominator;

    constructor(uint256 numerator_, uint256 denominator_) {
        numerator = numerator_;
        denominator = denominator_;
    }

    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        address[] calldata path,
        address to,
        uint256
    ) external returns (uint256[] memory amounts) {
        MockToken(path[0]).transferFrom(msg.sender, address(this), amountIn);
        uint256 amountOut = amountIn * numerator / denominator;
        require(amountOut >= amountOutMin, "slippage");
        MockToken(path[path.length - 1]).transfer(to, amountOut);
        amounts = new uint256[](path.length);
        amounts[0] = amountIn;
        amounts[path.length - 1] = amountOut;
    }
}

contract JayTradingBotFlashArbitrageTest {
    MockToken private tokenA;
    MockToken private tokenB;
    MockProvider private provider;
    MockPool private pool;
    MockV2Router private routerAB;
    MockV2Router private routerBA;
    JayTradingBotFlashArbitrage private bot;

    function setUp() public {
        tokenA = new MockToken();
        tokenB = new MockToken();
        provider = new MockProvider();
        pool = new MockPool();
        provider.setPool(address(pool));
        routerAB = new MockV2Router(11, 10);
        routerBA = new MockV2Router(51, 55);
        bot = new JayTradingBotFlashArbitrage(address(provider), address(this));

        bot.setTokenAllowed(address(tokenA), true);
        bot.setTokenAllowed(address(tokenB), true);
        bot.setRouterAllowed(address(routerAB), true);
        bot.setRouterAllowed(address(routerBA), true);

        tokenA.mint(address(pool), 1_000_000 ether);
        tokenB.mint(address(routerAB), 1_000_000 ether);
        tokenA.mint(address(routerBA), 1_000_000 ether);
    }

    function testProfitableRouteRepaysAaveAndPaysOnlyProfit() public {
        JayTradingBotFlashArbitrage.SwapLeg[] memory legs = _route();
        uint256 profit = bot.startFlashArbitrage(
            address(tokenA), 1_000 ether, legs, 19 ether, block.timestamp + 60, address(this)
        );

        require(profit == 19.1 ether, "wrong returned profit");
        require(tokenA.balanceOf(address(this)) == 19.1 ether, "profit not paid");
        require(tokenA.balanceOf(address(bot)) == 0, "bot retained funds");
    }

    function testUnprofitableRouteRevertsAtomically() public {
        MockV2Router badRouter = new MockV2Router(1, 2);
        tokenA.mint(address(badRouter), 1_000_000 ether);
        bot.setRouterAllowed(address(badRouter), true);

        JayTradingBotFlashArbitrage.SwapLeg[] memory legs = _routeWithSecond(badRouter);
        try bot.startFlashArbitrage(
            address(tokenA), 1_000 ether, legs, 1, block.timestamp + 60, address(this)
        ) {
            revert("expected revert");
        } catch {
            require(tokenA.balanceOf(address(this)) == 0, "unexpected payout");
            require(tokenA.balanceOf(address(bot)) == 0, "rollback failed");
        }
    }

    function _route() internal view returns (JayTradingBotFlashArbitrage.SwapLeg[] memory) {
        return _routeWithSecond(routerBA);
    }

    function _routeWithSecond(MockV2Router second)
        internal view returns (JayTradingBotFlashArbitrage.SwapLeg[] memory legs)
    {
        legs = new JayTradingBotFlashArbitrage.SwapLeg[](2);
        address[] memory pathAB = new address[](2);
        pathAB[0] = address(tokenA);
        pathAB[1] = address(tokenB);
        address[] memory pathBA = new address[](2);
        pathBA[0] = address(tokenB);
        pathBA[1] = address(tokenA);

        legs[0] = JayTradingBotFlashArbitrage.SwapLeg({
            kind: JayTradingBotFlashArbitrage.RouterKind.UniswapV2Compatible,
            router: address(routerAB),
            tokenIn: address(tokenA),
            tokenOut: address(tokenB),
            amountOutMinimum: 1_100 ether,
            route: abi.encode(pathAB)
        });
        legs[1] = JayTradingBotFlashArbitrage.SwapLeg({
            kind: JayTradingBotFlashArbitrage.RouterKind.UniswapV2Compatible,
            router: address(second),
            tokenIn: address(tokenB),
            tokenOut: address(tokenA),
            amountOutMinimum: 1,
            route: abi.encode(pathBA)
        });
    }
}
