#!/usr/bin/env python3
"""
Auto-sell monitor with continuous polling
Monitors wallet PnL and executes trades based on configurable thresholds
"""

import os
import sys
import asyncio
import argparse
import signal
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from dotenv import load_dotenv

# Add src to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from wallet_fetcher import fetch_wallet_pnl, TokenPnL
from auto_sell_command import (
    EnhancedProgressiveSellStrategy,
    execute_token_sell
)

load_dotenv()


class AutoSellMonitor:
    """
    Continuous monitoring system for automated selling based on PnL thresholds
    """

    def __init__(
        self,
        wallet_address: str,
        strategy: EnhancedProgressiveSellStrategy,
        polling_interval: int = 30,
        max_runtime_minutes: Optional[int] = None,
        dry_run: bool = False
    ):
        """
        Initialize the auto-sell monitor

        Args:
            wallet_address: Wallet to monitor
            strategy: Sell strategy to use
            polling_interval: Seconds between checks
            max_runtime_minutes: Maximum runtime in minutes (None for infinite)
            dry_run: If True, only analyze without executing trades
        """
        self.wallet_address = wallet_address
        self.strategy = strategy
        self.polling_interval = polling_interval
        self.max_runtime_minutes = max_runtime_minutes
        self.dry_run = dry_run

        # Track execution history to avoid duplicate sells
        self.executed_sells: Dict[str, List[Dict]] = {}  # token_address -> list of sells
        self.start_time = datetime.now()
        self.running = False
        self.total_trades_executed = 0
        self.total_profit_taken = 0.0
        self.total_loss_stopped = 0.0

    def should_continue_running(self) -> bool:
        """Check if monitor should continue running based on max runtime"""
        if not self.running:
            return False

        if self.max_runtime_minutes is None:
            return True

        elapsed = datetime.now() - self.start_time
        return elapsed < timedelta(minutes=self.max_runtime_minutes)

    def get_recent_sell_percentage(self, token_address: str, hours: int = 24) -> float:
        """
        Get total percentage sold for a token in recent hours
        Prevents over-selling the same token
        """
        if token_address not in self.executed_sells:
            return 0.0

        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_sells = [
            sell for sell in self.executed_sells[token_address]
            if sell['timestamp'] > cutoff_time
        ]

        return sum(sell['percentage'] for sell in recent_sells)

    async def analyze_and_execute_single_pass(self) -> Dict[str, Any]:
        """
        Single pass of analyzing wallet and executing trades
        """
        print(f"\n🔄 Checking wallet at {datetime.now().strftime('%H:%M:%S')}")

        try:
            # Fetch current PnL
            pnl_response = await fetch_wallet_pnl(self.wallet_address)

            if not pnl_response.tokens:
                print("  📭 No tokens found (excluding SOL/USDC)")
                return {"tokens_analyzed": 0, "trades_executed": 0}

            trades_executed = []

            for token in pnl_response.tokens:
                # Get sell decision with trailing stop support
                decision = self.strategy.get_sell_decision(
                    unrealized_percent=token.unrealized_percent,
                    token_address=token.address,
                    current_price=token.current_price
                )

                if decision["sell_percentage"] > 0:
                    # Check recent sells to avoid over-selling
                    recent_sell_pct = self.get_recent_sell_percentage(token.address)

                    # Limit total sells to 90% in 24h to keep some exposure
                    if recent_sell_pct >= 90:
                        print(f"  ⚠️ {token.symbol}: Already sold {recent_sell_pct:.0f}% "
                              f"in last 24h, skipping")
                        continue

                    # Adjust sell percentage if needed
                    adjusted_sell_pct = min(
                        decision["sell_percentage"],
                        90 - recent_sell_pct
                    )

                    if adjusted_sell_pct <= 0:
                        continue

                    print(f"  🎯 {token.symbol}: {decision['action']} - "
                          f"{token.unrealized_percent:+.1f}% unrealized")
                    print(f"     Selling {adjusted_sell_pct:.0f}% "
                          f"(${token.current_value * adjusted_sell_pct / 100:.2f})")

                    if not self.dry_run:
                        # Execute the trade
                        result = await execute_token_sell(token, adjusted_sell_pct)

                        if result["success"]:
                            # Track the execution
                            if token.address not in self.executed_sells:
                                self.executed_sells[token.address] = []

                            self.executed_sells[token.address].append({
                                'timestamp': datetime.now(),
                                'percentage': adjusted_sell_pct,
                                'unrealized_percent': token.unrealized_percent,
                                'value_usd': token.current_value * adjusted_sell_pct / 100
                            })

                            trades_executed.append({
                                'token': token.symbol,
                                 'action': decision['action'],
                                'sell_pct': adjusted_sell_pct
                            })

                            self.total_trades_executed += 1

                            if token.unrealized_percent > 0:
                                self.total_profit_taken += token.unrealized_usd * \
                                    (adjusted_sell_pct / 100)
                            else:
                                self.total_loss_stopped += abs(token.unrealized_usd * \
                                    (adjusted_sell_pct / 100))

                            print(f"     ✅ Trade executed successfully")
                        else:
                            print(f"     ❌ Trade failed: {result['error']}")
                    else:
                        print(f"     🔍 DRY RUN - Would execute trade")

            return {
                "tokens_analyzed": len(pnl_response.tokens),
                "trades_executed": len(trades_executed),
                "trades": trades_executed,
                "portfolio_value": pnl_response.total_current_value,
                "unrealized_pct": pnl_response.total_unrealized_percent
            }

        except Exception as e:
            print(f"  ❌ Error during analysis: {str(e)}")
            return {"error": str(e), "tokens_analyzed": 0, "trades_executed": 0}

    async def run_monitor(self):
        """
        Main monitoring loop
        """
        self.running = True
        print(f"🚀 Starting Auto-Sell Monitor")
        print(f"📊 Wallet: {self.wallet_address[:8]}...")
        print(f"⏱️ Polling every {self.polling_interval} seconds")

        if self.max_runtime_minutes:
            print(f"⏰ Max runtime: {self.max_runtime_minutes} minutes")
        else:
            print(f"♾️ Running indefinitely (press Ctrl+C to stop)")

        print(f"🎯 Stop Loss: {self.strategy.loss_threshold}%")
        print(f"📈 Profit Tiers:")
        for profit_pct, sell_pct in self.strategy.profit_tiers:
            multiplier = 1 + (profit_pct / 100)
            print(f"   {multiplier:.1f}x (+{profit_pct}%) → Sell {sell_pct}%")

        if self.dry_run:
            print("🔍 DRY RUN MODE - No trades will be executed")

        print("=" * 60)

        pass_count = 0

        try:
            while self.should_continue_running():
                pass_count += 1

                # Execute analysis pass
                result = await self.analyze_and_execute_single_pass()

                if result.get("trades_executed", 0) > 0:
                    print(f"  📊 Executed {result['trades_executed']} trades")

                # Show periodic summary every 10 passes
                if pass_count % 10 == 0:
                    self.print_summary()

                # Wait for next interval
                if self.should_continue_running():
                    await asyncio.sleep(self.polling_interval)

        except KeyboardInterrupt:
            print("\n⛔ Monitor stopped by user")
        finally:
            self.running = False
            self.print_final_summary()

    def print_summary(self):
        """Print monitoring summary"""
        runtime = datetime.now() - self.start_time
        print(f"\n📊 Monitoring Summary (Runtime: {runtime})")
        print(f"   Total Trades: {self.total_trades_executed}")
        print(f"   Profit Taken: ${self.total_profit_taken:.2f}")
        print(f"   Losses Stopped: ${self.total_loss_stopped:.2f}")
        print("=" * 60)

    def print_final_summary(self):
        """Print final summary when stopping"""
        runtime = datetime.now() - self.start_time
        print("\n" + "=" * 60)
        print("📊 FINAL SUMMARY")
        print(f"   Runtime: {runtime}")
        print(f"   Total Trades Executed: {self.total_trades_executed}")
        print(f"   Total Profit Taken: ${self.total_profit_taken:.2f}")
        print(f"   Total Losses Stopped: ${self.total_loss_stopped:.2f}")
        print(f"   Net Result: ${self.total_profit_taken - self.total_loss_stopped:+.2f}")

        if self.executed_sells:
            print("\n   Tokens Traded:")
            for token_addr, sells in self.executed_sells.items():
                total_pct = sum(s['percentage'] for s in sells)
                print(f"   - {token_addr[:8]}...: {len(sells)} trades, "
                      f"{total_pct:.0f}% total sold")
        print("=" * 60)


def main():
    """Main command line interface"""
    parser = argparse.ArgumentParser(
        description="Continuously monitor wallet PnL and execute automated sells"
    )

    parser.add_argument(
        "--wallet",
        type=str,
        default=None,
        help="Wallet address to monitor (defaults to DELEGATED_WALLET_ADDRESS env var)"
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Polling interval in seconds (default: 30)"
    )

    parser.add_argument(
        "--runtime",
        type=int,
        default=None,
        help="Maximum runtime in minutes (default: run indefinitely)"
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
             "profit1:sell1,profit2:sell2,... (e.g., '30:30,100:30,200:25,900:15')"
    )

    args = parser.parse_args()

    # Get wallet address
    wallet_address = args.wallet or os.getenv("DELEGATED_WALLET_ADDRESS")

    if not wallet_address:
        print("❌ Error: No wallet address provided.")
        print("   Use --wallet <address> or set DELEGATED_WALLET_ADDRESS environment variable")
        sys.exit(1)

    # Parse profit tiers
    profit_tiers = None
    if args.profit_tiers:
        try:
            profit_tiers = []
            for tier in args.profit_tiers.split(','):
                profit_str, sell_str = tier.strip().split(':')
                profit_tiers.append((float(profit_str), float(sell_str)))
        except Exception as e:
            print(f"❌ Error parsing profit tiers: {str(e)}")
            sys.exit(1)

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

    # Setup signal handler for clean shutdown
    def signal_handler(signum, frame):
        monitor.running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the monitor
    asyncio.run(monitor.run_monitor())


if __name__ == "__main__":
    main()