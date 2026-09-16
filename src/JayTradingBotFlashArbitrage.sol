// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20 {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
}

interface IAavePoolAddressesProvider {
    function getPool() external view returns (address);
}

interface IAavePool {
    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

interface IFlashLoanSimpleReceiver {
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}

interface IUniswapV2Router {
    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        address[] calldata path,
        address to,
        uint256 deadline
    ) external returns (uint256[] memory amounts);
}

interface IUniswapV3SwapRouter {
    struct ExactInputParams {
        bytes path;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
    }

    function exactInput(ExactInputParams calldata params) external returns (uint256 amountOut);
}

/// @title JayTradingBot Flash Arbitrage Executor
/// @notice Executes an owner-supplied, pre-quoted route using an Aave V3 flash loan.
/// @dev This contract does not discover opportunities. An off-chain searcher must quote and simulate routes.
contract JayTradingBotFlashArbitrage is IFlashLoanSimpleReceiver {
    enum RouterKind { UniswapV2Compatible, UniswapV3Compatible }

    struct SwapLeg {
        RouterKind kind;
        address router;
        address tokenIn;
        address tokenOut;
        uint256 amountOutMinimum;
        bytes route;
    }

    struct CallbackData {
        SwapLeg[] legs;
        uint256 minimumProfit;
        uint256 deadline;
        uint256 balanceBefore;
        address profitRecipient;
    }

    address public owner;
    IAavePoolAddressesProvider public immutable addressesProvider;
    bool public paused;

    mapping(address => bool) public allowedRouters;
    mapping(address => bool) public allowedTokens;

    uint256 private locked = 1;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event RouterPermissionSet(address indexed router, bool allowed);
    event TokenPermissionSet(address indexed token, bool allowed);
    event PauseSet(bool paused);
    event FlashArbitrageExecuted(
        address indexed asset,
        uint256 borrowed,
        uint256 premium,
        uint256 profit,
        address indexed profitRecipient
    );
    event Rescue(address indexed token, address indexed recipient, uint256 amount);

    error NotOwner();
    error UnauthorizedPool();
    error UnauthorizedInitiator();
    error Paused();
    error Reentrancy();
    error InvalidAddress();
    error InvalidAmount();
    error InvalidDeadline();
    error InvalidRoute();
    error RouterNotAllowed(address router);
    error TokenNotAllowed(address token);
    error InsufficientProfit(uint256 actual, uint256 required);
    error TokenOperationFailed();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier nonReentrant() {
        if (locked != 1) revert Reentrancy();
        locked = 2;
        _;
        locked = 1;
    }

    constructor(address provider, address initialOwner) {
        if (provider == address(0) || initialOwner == address(0)) revert InvalidAddress();
        addressesProvider = IAavePoolAddressesProvider(provider);
        owner = initialOwner;
        emit OwnershipTransferred(address(0), initialOwner);
    }

    function setRouterAllowed(address router, bool allowed) external onlyOwner {
        if (router == address(0)) revert InvalidAddress();
        allowedRouters[router] = allowed;
        emit RouterPermissionSet(router, allowed);
    }

    function setTokenAllowed(address token, bool allowed) external onlyOwner {
        if (token == address(0)) revert InvalidAddress();
        allowedTokens[token] = allowed;
        emit TokenPermissionSet(token, allowed);
    }

    function setPaused(bool value) external onlyOwner {
        paused = value;
        emit PauseSet(value);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert InvalidAddress();
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    /// @notice Starts an atomic Aave flash-loan route. Reverts unless minimumProfit is achieved.
    /// @param asset Asset borrowed from Aave and required as the final route output.
    /// @param amount Flash-loan principal.
    /// @param legs Pre-quoted swaps. V2 route = abi.encode(address[]); V3 route = packed path bytes.
    /// @param minimumProfit Minimum asset units left after principal and premium.
    /// @param deadline Timestamp after which execution reverts.
    /// @param profitRecipient Address receiving profit after Aave pulls repayment.
    function startFlashArbitrage(
        address asset,
        uint256 amount,
        SwapLeg[] calldata legs,
        uint256 minimumProfit,
        uint256 deadline,
        address profitRecipient
    ) external onlyOwner nonReentrant returns (uint256 profit) {
        if (paused) revert Paused();
        if (asset == address(0) || profitRecipient == address(0)) revert InvalidAddress();
        if (amount == 0) revert InvalidAmount();
        if (deadline < block.timestamp) revert InvalidDeadline();
        if (!allowedTokens[asset]) revert TokenNotAllowed(asset);
        _validateRoute(asset, legs);

        uint256 balanceBefore = IERC20(asset).balanceOf(address(this));
        bytes memory params = abi.encode(
            CallbackData({
                legs: legs,
                minimumProfit: minimumProfit,
                deadline: deadline,
                balanceBefore: balanceBefore,
                profitRecipient: profitRecipient
            })
        );

        IAavePool(addressesProvider.getPool()).flashLoanSimple(
            address(this), asset, amount, params, 0
        );

        uint256 balanceAfter = IERC20(asset).balanceOf(address(this));
        profit = balanceAfter - balanceBefore;
        _safeTransfer(asset, profitRecipient, profit);
    }

    /// @inheritdoc IFlashLoanSimpleReceiver
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external returns (bool) {
        address pool = addressesProvider.getPool();
        if (msg.sender != pool) revert UnauthorizedPool();
        if (initiator != address(this)) revert UnauthorizedInitiator();
        if (paused) revert Paused();

        CallbackData memory data = abi.decode(params, (CallbackData));
        if (data.deadline < block.timestamp) revert InvalidDeadline();

        uint256 currentAmount = amount;
        for (uint256 i; i < data.legs.length; ++i) {
            currentAmount = _executeLeg(data.legs[i], currentAmount, data.deadline);
        }

        uint256 debt = amount + premium;
        uint256 finalBalance = IERC20(asset).balanceOf(address(this));
        uint256 requiredBalance = data.balanceBefore + debt + data.minimumProfit;
        if (finalBalance < requiredBalance) {
            revert InsufficientProfit(finalBalance, requiredBalance);
        }

        _forceApprove(asset, pool, debt);
        emit FlashArbitrageExecuted(
            asset, amount, premium, finalBalance - data.balanceBefore - debt, data.profitRecipient
        );
        return true;
    }

    function rescueToken(address token, address recipient, uint256 amount) external onlyOwner {
        if (recipient == address(0)) revert InvalidAddress();
        _safeTransfer(token, recipient, amount);
        emit Rescue(token, recipient, amount);
    }

    function _validateRoute(address asset, SwapLeg[] calldata legs) internal view {
        if (legs.length < 2 || legs.length > 8) revert InvalidRoute();
        address expected = asset;
        for (uint256 i; i < legs.length; ++i) {
            SwapLeg calldata leg = legs[i];
            if (!allowedRouters[leg.router]) revert RouterNotAllowed(leg.router);
            if (!allowedTokens[leg.tokenIn]) revert TokenNotAllowed(leg.tokenIn);
            if (!allowedTokens[leg.tokenOut]) revert TokenNotAllowed(leg.tokenOut);
            if (leg.tokenIn != expected || leg.tokenIn == leg.tokenOut) revert InvalidRoute();
            expected = leg.tokenOut;
        }
        if (expected != asset) revert InvalidRoute();
    }

    function _executeLeg(
        SwapLeg memory leg,
        uint256 amountIn,
        uint256 deadline
    ) internal returns (uint256 amountOut) {
        _forceApprove(leg.tokenIn, leg.router, amountIn);

        if (leg.kind == RouterKind.UniswapV2Compatible) {
            address[] memory path = abi.decode(leg.route, (address[]));
            if (
                path.length < 2 || path[0] != leg.tokenIn ||
                path[path.length - 1] != leg.tokenOut
            ) revert InvalidRoute();
            uint256[] memory amounts = IUniswapV2Router(leg.router).swapExactTokensForTokens(
                amountIn, leg.amountOutMinimum, path, address(this), deadline
            );
            amountOut = amounts[amounts.length - 1];
        } else {
            if (
                leg.route.length < 43 || _firstToken(leg.route) != leg.tokenIn ||
                _lastToken(leg.route) != leg.tokenOut
            ) revert InvalidRoute();
            amountOut = IUniswapV3SwapRouter(leg.router).exactInput(
                IUniswapV3SwapRouter.ExactInputParams({
                    path: leg.route,
                    recipient: address(this),
                    deadline: deadline,
                    amountIn: amountIn,
                    amountOutMinimum: leg.amountOutMinimum
                })
            );
        }

        _forceApprove(leg.tokenIn, leg.router, 0);
    }

    function _firstToken(bytes memory path) internal pure returns (address token) {
        assembly { token := shr(96, mload(add(path, 32))) }
    }

    function _lastToken(bytes memory path) internal pure returns (address token) {
        uint256 start = path.length + 12;
        assembly { token := shr(96, mload(add(path, start))) }
    }

    function _safeTransfer(address token, address to, uint256 amount) internal {
        (bool ok, bytes memory result) = token.call(
            abi.encodeCall(IERC20.transfer, (to, amount))
        );
        if (!ok || (result.length != 0 && !abi.decode(result, (bool)))) {
            revert TokenOperationFailed();
        }
    }

    function _forceApprove(address token, address spender, uint256 amount) internal {
        (bool ok, bytes memory result) = token.call(
            abi.encodeCall(IERC20.approve, (spender, amount))
        );
        if (ok && (result.length == 0 || abi.decode(result, (bool)))) return;

        (ok, result) = token.call(abi.encodeCall(IERC20.approve, (spender, 0)));
        if (!ok || (result.length != 0 && !abi.decode(result, (bool)))) {
            revert TokenOperationFailed();
        }
        (ok, result) = token.call(abi.encodeCall(IERC20.approve, (spender, amount)));
        if (!ok || (result.length != 0 && !abi.decode(result, (bool)))) {
            revert TokenOperationFailed();
        }
    }
}
