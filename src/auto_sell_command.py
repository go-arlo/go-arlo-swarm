#!/usr/bin/env python3
"""
Auto-sell command that analyzes wallet PnL and executes trades based on thresholds.
Looks up PnL for each token, determines sell decisions, and executes swaps to SOL.
"""

import os
import sys
import asyncio
import argparse
from typing import Dict, Any, List
from dotenv import load_dotenv

# Add src to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from wallet_fetcher import (
    fetch_wallet_pnl,
    TokenPnL,
    get_sol_balance
)

from trading_tools import ExecuteJupiterSwap

load_dotenv()


class EnhancedProgressiveSellStrategy:
    """
    Enhanced progressive sell strategy with trailing stop functionality
    """

    def __init__(self,
                 loss_threshold: float = -10.0,
                 profit_tiers: list = None,
                 trailing_stop_activation: float = 60.0,
                 trailing_stop_distance: float = 12.0):
        """
        Initialize enhanced progressive sell strategy with trailing stop

        Args:
            loss_threshold: Stop loss percentage (default: -10%)
            profit_tiers: List of (profit_percent, sell_percentage) tuples
                         Default: [(30, 30), (100, 30), (200, 25), (900, 15)]
                         which means: 1.3x (+30%) sell 30%,
                                     2x (+100%) sell 30%,
                                     3x (+200%) sell 25%,
                                     10x (+900%) sell remaining 15%
            trailing_stop_activation: Profit % to activate trailing stop (default: 60%)
            trailing_stop_distance: Distance for trailing stop in % (default: 12%)
        """
        self.loss_threshold = loss_threshold
        self.trailing_stop_activation = trailing_stop_activation
        self.trailing_stop_distance = trailing_stop_distance

        # Track highest prices for trailing stop
        self.peak_prices = {}  # token_address -> highest_price
        self.trailing_stops_active = {}  # token_address -> bool

        # Default profit tiers with trailing stop strategy
        if profit_tiers is None:
            self.profit_tiers = [
                (30.0, 30.0),   # +30% profit - sell 30%
                (100.0, 30.0),  # 2x (+100%) - sell 30%
                (200.0, 25.0),  # 3x (+200%) - sell 25%
                (900.0, 15.0)   # 10x (+900%) - force exit remaining 15%
            ]
        else:
            # Validate and sort custom tiers (max 5 tiers)
            if len(profit_tiers) > 5:
                raise ValueError("Maximum 5 profit tiers allowed")
            # Sort by profit percentage ascending
            self.profit_tiers = sorted(profit_tiers, key=lambda x: x[0])

            # Validate sell percentages sum to <= 100%
            total_sell = sum(tier[1] for tier in self.profit_tiers)
            if total_sell > 100:
                raise ValueError(f"Total sell percentages ({total_sell}%) exceed 100%")

    def update_trailing_stop(self, token_address: str, current_price: float,
                           unrealized_percent: float) -> None:
        """
        Update trailing stop tracking for a token

        Args:
            token_address: Token contract address
            current_price: Current token price
            unrealized_percent: Current unrealized profit percentage
        """
        # Check if trailing stop should be activated
        if unrealized_percent >= self.trailing_stop_activation:
            if token_address not in self.trailing_stops_active:
                self.trailing_stops_active[token_address] = True
                self.peak_prices[token_address] = current_price
                print(f"     📈 Trailing stop activated at {unrealized_percent:.1f}%")
            else:
                # Update peak price if current is higher
                if token_address not in self.peak_prices or current_price > self.peak_prices[token_address]:
                    self.peak_prices[token_address] = current_price

    def check_trailing_stop(self, token_address: str, current_price: float) -> bool:
        """
        Check if trailing stop has been hit

        Args:
            token_address: Token contract address
            current_price: Current token price

        Returns:
            True if trailing stop triggered, False otherwise
        """
        if token_address not in self.trailing_stops_active:
            return False

        if token_address not in self.peak_prices:
            return False

        peak_price = self.peak_prices[token_address]
        drop_from_peak = ((peak_price - current_price) / peak_price) * 100

        return drop_from_peak >= self.trailing_stop_distance

    def get_sell_decision(self, unrealized_percent: float, token_address: str = None,
                         current_price: float = None) -> Dict[str, Any]:
        """
        Get detailed sell decision based on profit tiers, stop loss, and trailing stop

        Args:
            unrealized_percent: Current unrealized profit percentage
            token_address: Token contract address (for trailing stop)
            current_price: Current token price (for trailing stop)

        Returns:
            Dict with sell_percentage, action, reason, and threshold_range
        """
        # Update trailing stop if we have price info
        if token_address and current_price:
            self.update_trailing_stop(token_address, current_price, unrealized_percent)

        # Check trailing stop first (if active)
        if token_address and current_price and self.check_trailing_stop(token_address, current_price):
            peak_price = self.peak_prices.get(token_address, current_price)
            drop_pct = ((peak_price - current_price) / peak_price) * 100
            return {
                "sell_percentage": 100.0,
                "action": "TRAILING_STOP",
                "reason": f"Trailing stop hit: -{drop_pct:.1f}% from peak",
                "threshold_range": f"Trailing stop at {self.trailing_stop_distance}% from peak"
            }

        # Hard stop loss logic
        if unrealized_percent <= self.loss_threshold:
            return {
                "sell_percentage": 100.0,
                "action": "STOP_LOSS",
                "reason": f"Stop loss triggered at {unrealized_percent:.1f}%",
                "threshold_range": f"{self.loss_threshold}% or worse"
            }

        # Check profit tiers
        for i, (profit_threshold, sell_pct) in enumerate(self.profit_tiers):
            if unrealized_percent >= profit_threshold:
                # Check if this is the highest tier (force exit at 10x)
                is_highest = (i == len(self.profit_tiers) - 1)

                if is_highest:
                    # Force full exit at 10x
                    multiplier = 1 + (profit_threshold / 100)
                    return {
                        "sell_percentage": sell_pct,
                        "action": "FORCE_EXIT",
                        "reason": f"Force exit at {multiplier:.1f}x ({unrealized_percent:.1f}%)",
                        "threshold_range": f"+{profit_threshold}% or better"
                    }
                else:
                    # Check if we're below the next tier
                    next_threshold = self.profit_tiers[i + 1][0]
                    if unrealized_percent < next_threshold:
                        multiplier = 1 + (profit_threshold / 100)
                        next_multiplier = 1 + (next_threshold / 100)
                        return {
                            "sell_percentage": sell_pct,
                            "action": "TAKE_PROFIT",
                            "reason": f"Take profit at {multiplier:.1f}x ({unrealized_percent:.1f}%)",
                            "threshold_range": f"+{profit_threshold}% to +{next_threshold - 0.1}%"
                        }

        # If no profit tier matches, hold
        lowest_profit_tier = self.profit_tiers[0][0] if self.profit_tiers else 30.0
        return {
            "sell_percentage": 0.0,
            "action": "HOLD",
            "reason": f"Within hold range at {unrealized_percent:.1f}%",
            "threshold_range": f"{self.loss_threshold + 0.1}% to +{lowest_profit_tier - 0.1}%"
        }

    def generate_sell_signals(self, tokens: List[TokenPnL]) -> List[Dict[str, Any]]:
        """
        Generate sell signals for tokens based on their unrealized PnL
        Compatible with wallet_router.py expectations
        """
        sell_signals = []

        for token in tokens:
            # Pass token address and current price for trailing stop
            decision = self.get_sell_decision(
                unrealized_percent=token.unrealized_percent,
                token_address=token.address,
                current_price=token.current_price
            )

            if decision["sell_percentage"] > 0:
                sell_amount = token.holding * (decision["sell_percentage"] / 100.0)

                sell_signals.append({
                    "token": token.symbol,
                    "address": token.address,
                    "action": decision["action"],
                    "reason": decision["reason"],
                    "unrealized_percent": token.unrealized_percent,
                    "sell_percentage": decision["sell_percentage"],
                    "current_holding": token.holding,
                    "sell_amount": sell_amount,
                    "current_value_usd": token.current_value,
                    "unrealized_usd": token.unrealized_usd,
                    "threshold_range": decision["threshold_range"]
                })

        return sell_signals


async def execute_token_sell(token: TokenPnL, sell_percentage: float) -> Dict[str, Any]:
    """
    Execute the actual token sale by swapping to SOL

    Args:
        token: Token PnL data
        sell_percentage: Percentage of holding to sell

    Returns:
        Dict with execution results
    """
    try:
        # Check SOL balance for transaction fees
        sol_balance = get_sol_balance() or 0.0
        fee_reserve = 0.005  # Reserve 0.005 SOL for transaction fees

        if sol_balance < fee_reserve:
            return {
                "success": False,
                "sell_amount": 0,
                "sell_amount_raw": 0,
                "execution_result": None,
                "error": f"Insufficient SOL balance for transaction fees. Need {fee_reserve} SOL, have {sol_balance:.6f} SOL"
            }

        # Calculate amount to sell
        sell_amount = token.holding * (sell_percentage / 100.0)

        # Convert to smallest unit (multiply by 10^decimals)
        sell_amount_raw = int(sell_amount * (10 ** token.decimals))

        print(f"  🔄 Executing {sell_percentage}% sale of {token.symbol}...")
        print(f"     Selling {sell_amount:.6f} {token.symbol} ({sell_amount_raw} raw units)")
        print(f"     SOL Balance: {sol_balance:.6f} SOL (fee reserve: {fee_reserve} SOL)")

        # Create swap tool
        swap_tool = ExecuteJupiterSwap(
            input_mint=token.address,  # Token to sell
            output_mint="So11111111111111111111111111111111111111112",  # SOL mint
            amount=str(sell_amount_raw),
            slippage_bps=100  # 1% slippage
        )

        # Execute the swap
        result = swap_tool.run()

        # Check if swap was successful by looking for error indicators
        if result.startswith("❌") or "failed:" in result.lower() or "error:" in result.lower():
            # Check if it's a dead token
            if "dead" in result.lower() or "no liquidity" in result.lower() or "no routes" in result.lower():
                return {
                    "success": False,
                    "sell_amount": sell_amount,
                    "sell_amount_raw": sell_amount_raw,
                    "execution_result": result,
                    "error": "Token is dead or has no liquidity",
                    "is_dead": True
                }
            return {
                "success": False,
                "sell_amount": sell_amount,
                "sell_amount_raw": sell_amount_raw,
                "execution_result": result,
                "error": result
            }

        return {
            "success": True,
            "sell_amount": sell_amount,
            "sell_amount_raw": sell_amount_raw,
            "execution_result": result,
            "error": None
        }

    except Exception as e:
        error_str = str(e).lower()
        is_dead = "no liquidity" in error_str or "no routes" in error_str or "dead" in error_str
        return {
            "success": False,
            "sell_amount": 0,
            "sell_amount_raw": 0,
            "execution_result": None,
            "error": str(e),
            "is_dead": is_dead
        }


async def analyze_and_execute_wallet_sells(
    wallet_address: str,
    dry_run: bool = False,
    loss_threshold: float = -15.0,
    profit_tiers: list = None
) -> Dict[str, Any]:
    """
    Analyze wallet PnL and execute sell decisions

    Args:
        wallet_address: Wallet address to analyze
        dry_run: If True, only analyze without executing trades
        loss_threshold: Loss percentage threshold for stop loss
        profit_tiers: List of (profit_percent, sell_percentage) tuples

    Returns:
        Dict with analysis results and execution outcomes
    """
    print(f"🔍 Analyzing wallet PnL for {wallet_address[:8]}...")
    print(f"📊 Stop Loss: {loss_threshold}%")

    # Display profit tiers
    if profit_tiers:
        print("📈 Profit Tiers:")
        for profit_pct, sell_pct in profit_tiers:
            multiplier = 1 + (profit_pct / 100)
            print(f"   {multiplier:.1f}x (+{profit_pct}%) → Sell {sell_pct}%")
    else:
        print("📈 Using default profit tiers:")
        print("   1.3x (+30%) → Sell 30%")
        print("   2.0x (+100%) → Sell 30%")
        print("   3.0x (+200%) → Sell 25%")
        print("   10.0x (+900%) → Force exit 15%")
        print("🛡️ Risk Controls:")
        print("   Hard stop loss: -10%")
        print("   Trailing stop: Activates at +60%, distance 12%")

    try:
        # Fetch wallet PnL data
        pnl_response = await fetch_wallet_pnl(wallet_address)

        if not pnl_response.tokens:
            return {
                "success": False,
                "error": "No tokens found in wallet (excluding SOL/USDC)",
                "tokens_analyzed": 0,
                "tokens_sold": 0,
                "total_trades": 0
            }

        # Initialize strategy
        strategy = EnhancedProgressiveSellStrategy(
            loss_threshold=loss_threshold,
            profit_tiers=profit_tiers
        )

        # Analyze each token
        analysis_results = []
        executed_trades = []
        tokens_to_sell = 0

        print(f"\n📋 Token Analysis Results:")
        print("=" * 80)

        for token in pnl_response.tokens:
            # Get sell decision with trailing stop support
            decision = strategy.get_sell_decision(
                unrealized_percent=token.unrealized_percent,
                token_address=token.address,
                current_price=token.current_price
            )

            # Determine if we should sell
            should_sell = decision["sell_percentage"] > 0
            if should_sell:
                tokens_to_sell += 1

            # Display decision
            status_emoji = "🔴" if decision["action"] == "STOP_LOSS" else "🟢" if should_sell else "🟡"
            print(f"{status_emoji} {token.symbol} | {token.unrealized_percent:+6.1f}% | {decision['action']:12} | {decision['threshold_range']}")

            if should_sell:
                print(f"   💰 Current Value: ${token.current_value:.2f} | Unrealized: ${token.unrealized_usd:+.2f}")
                print(f"   📤 Sell Decision: {decision['sell_percentage']:.0f}% ({decision['reason']})")

                # Execute trade if not dry run
                if not dry_run:
                    execution_result = await execute_token_sell(token, decision["sell_percentage"])
                    executed_trades.append({
                        "token": token.symbol,
                        "address": token.address,
                        "decision": decision,
                        "execution": execution_result
                    })

                    if execution_result["success"]:
                        print(f"   ✅ Trade executed successfully")
                        print(f"   📝 Result: {execution_result['execution_result']}")
                    else:
                        if execution_result.get("is_dead"):
                            print(f"   💀 Token appears dead: No liquidity or trading routes available")
                            print(f"      This token cannot be sold as it has no active market")
                        else:
                            print(f"   ❌ Trade failed: {execution_result['error']}")
                else:
                    print(f"   🔍 DRY RUN - Would execute {decision['sell_percentage']:.0f}% sell")
            else:
                print(f"   💎 Holding: {decision['reason']}")

            analysis_results.append({
                "token": token.symbol,
                "address": token.address,
                "unrealized_percent": token.unrealized_percent,
                "unrealized_usd": token.unrealized_usd,
                "current_value": token.current_value,
                "holding": token.holding,
                "decision": decision,
                "should_sell": should_sell
            })

            print()  # Empty line for readability

        # Summary
        successful_trades = len([t for t in executed_trades if t["execution"]["success"]])
        failed_trades = len([t for t in executed_trades if not t["execution"]["success"]])

        print("=" * 80)
        print(f"📊 SUMMARY:")
        print(f"   Total Tokens Analyzed: {len(pnl_response.tokens)}")
        print(f"   Tokens with Sell Signals: {tokens_to_sell}")
        print(f"   Portfolio Unrealized PnL: ${pnl_response.total_unrealized_usd:+,.2f} ({pnl_response.total_unrealized_percent:+.2f}%)")

        if not dry_run:
            print(f"   Trades Executed: {len(executed_trades)}")
            print(f"   Successful: {successful_trades} | Failed: {failed_trades}")
        else:
            print(f"   DRY RUN MODE - No trades executed")

        return {
            "success": True,
            "wallet_address": wallet_address,
            "total_tokens": len(pnl_response.tokens),
            "tokens_with_sell_signals": tokens_to_sell,
            "portfolio_unrealized_usd": pnl_response.total_unrealized_usd,
            "portfolio_unrealized_percent": pnl_response.total_unrealized_percent,
            "analysis_results": analysis_results,
            "executed_trades": executed_trades,
            "successful_trades": successful_trades,
            "failed_trades": failed_trades,
            "dry_run": dry_run
        }

    except Exception as e:
        print(f"❌ Error analyzing wallet: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "wallet_address": wallet_address
        }


def main():
    """Main command line interface"""
    parser = argparse.ArgumentParser(
        description="Analyze wallet PnL and execute automated sells based on thresholds"
    )

    parser.add_argument(
        "--wallet",
        type=str,
        default=None,
        help="Wallet address to analyze (defaults to DELEGATED_WALLET_ADDRESS env var)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only analyze without executing trades"
    )

    parser.add_argument(
        "--loss-threshold",
        type=float,
        default=-10.0,
        help="Loss percentage threshold for stop loss (default: -10.0)"
    )

    parser.add_argument(
        "--profit-tiers",
        type=str,
        default=None,
        help="Custom profit tiers as comma-separated pairs: "
             "profit1:sell1,profit2:sell2,... (e.g., '30:30,100:30,200:25,900:15') "
             "Max 5 tiers allowed. Defaults to 1.3x:30%%, 2x:30%%, 3x:25%%, 10x:15%%"
    )

    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Run in monitoring mode with continuous polling"
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Polling interval in seconds for monitor mode (default: 60)"
    )

    parser.add_argument(
        "--runtime",
        type=int,
        default=None,
        help="Maximum runtime in minutes for monitor mode (default: indefinite)"
    )

    args = parser.parse_args()

    # Get wallet address
    wallet_address = args.wallet or os.getenv("DELEGATED_WALLET_ADDRESS")

    if not wallet_address:
        print("❌ Error: No wallet address provided.")
        print("   Use --wallet <address> or set DELEGATED_WALLET_ADDRESS environment variable")
        sys.exit(1)

    # Check required environment variables
    if not args.dry_run:
        required_vars = ["BIRDEYE_API_KEY"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]

        if missing_vars:
            print(f"❌ Error: Missing required environment variables: {', '.join(missing_vars)}")
            sys.exit(1)

    # Parse profit tiers if provided
    profit_tiers = None
    if args.profit_tiers:
        try:
            profit_tiers = []
            for tier in args.profit_tiers.split(','):
                profit_str, sell_str = tier.strip().split(':')
                profit_tiers.append((float(profit_str), float(sell_str)))

            if len(profit_tiers) > 5:
                print("❌ Error: Maximum 5 profit tiers allowed")
                sys.exit(1)

            # Validate total sell percentage
            total_sell = sum(tier[1] for tier in profit_tiers)
            if total_sell > 100:
                print(f"❌ Error: Total sell percentages ({total_sell}%) exceed 100%")
                sys.exit(1)
        except Exception as e:
            print(f"❌ Error parsing profit tiers: {str(e)}")
            print("   Format: profit1:sell1,profit2:sell2,...")
            print("   Example: 50:20,100:50,200:20,900:10")
            sys.exit(1)

    # Check if running in monitor mode
    if args.monitor:
        # Import and run the monitor
        from auto_sell_monitor import AutoSellMonitor

        print("🔄 Starting in MONITOR MODE")

        # Create strategy
        strategy = EnhancedProgressiveSellStrategy(
            loss_threshold=args.loss_threshold,
            profit_tiers=profit_tiers
        )

        # Create and run monitor
        monitor = AutoSellMonitor(
            wallet_address=wallet_address,
            strategy=strategy,
            polling_interval=args.interval,
            max_runtime_minutes=args.runtime,
            dry_run=args.dry_run
        )

        asyncio.run(monitor.run_monitor())
    else:
        # Run single analysis
        print("🚀 Starting Automated Wallet PnL Analysis and Sell Execution")
        print("=" * 80)

        result = asyncio.run(
            analyze_and_execute_wallet_sells(
                wallet_address=wallet_address,
                dry_run=args.dry_run,
                loss_threshold=args.loss_threshold,
                profit_tiers=profit_tiers
            )
        )

        if result["success"]:
            print("\n🎉 Analysis completed successfully!")
            if not args.dry_run and result.get("executed_trades"):
                print(f"💼 Executed {result['successful_trades']} successful trades")
        else:
            print(f"\n💥 Analysis failed: {result.get('error', 'Unknown error')}")
            sys.exit(1)


if __name__ == "__main__":
    main()