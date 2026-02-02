#!/usr/bin/env python
"""
Comprehensive Trading System
Complete automated trading with token discovery, analysis, buying, and auto-selling
"""

import asyncio
import json
import os
import sys
import argparse
import signal
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import existing components
from token_list_fetcher import TokenListPresets, fetch_token_list, filter_by_volume_liquidity_ratio
from wallet_fetcher import check_token_balance, get_sol_balance, fetch_wallet_pnl
from rejection_tracker import get_rejection_tracker
from data_fetchers import fetch_all_token_data
from trading_analyzer import (
    TradingAnalyzer,
    get_moderate_criteria,
    get_conservative_criteria,
    get_aggressive_criteria,
    get_strict_default_criteria,
    RiskLevel,
    ConcentrationLevel
)
from trading_tools import AutoExecuteSwap
from auto_sell_command import EnhancedProgressiveSellStrategy, execute_token_sell


class ComprehensiveTradingSystem:
    """Complete trading system with buying and selling capabilities"""

    def __init__(
        self,
        dry_run: bool = True,
        risk_profile: str = "strict",
        enable_auto_sell: bool = False,
        sell_check_interval: int = 30,
        loss_threshold: float = -10.0,
        profit_tiers: list = None,
        max_trade_amount: float = None
    ):
        """
        Initialize the comprehensive trading system

        Args:
            dry_run: If True, simulate trades without executing
            risk_profile: "strict" (default), "conservative", "moderate", or "aggressive"
            enable_auto_sell: Enable automatic selling based on PnL
            sell_check_interval: Seconds between sell checks
            loss_threshold: Stop loss percentage
            profit_tiers: Custom profit-taking tiers
            max_trade_amount: Maximum amount in SOL per trade (overrides MAX_AMOUNT env var)
        """
        self.dry_run = dry_run
        self.enable_auto_sell = enable_auto_sell
        self.sell_check_interval = sell_check_interval
        self.max_trade_amount = max_trade_amount

        self.rejection_tracker = get_rejection_tracker()

        # Set up risk profile - STRICT is the default
        if risk_profile == "conservative":
            self.trading_analyzer = TradingAnalyzer(get_conservative_criteria(), debug=True)
        elif risk_profile == "moderate":
            self.trading_analyzer = TradingAnalyzer(get_moderate_criteria(), debug=True)
        elif risk_profile == "aggressive":
            self.trading_analyzer = TradingAnalyzer(get_aggressive_criteria(), debug=True)
        else:  # Default to strict
            self.trading_analyzer = TradingAnalyzer(get_strict_default_criteria(), debug=True)

        if enable_auto_sell:
            self.sell_strategy = EnhancedProgressiveSellStrategy(
                loss_threshold=loss_threshold,
                profit_tiers=profit_tiers
            )
        else:
            self.sell_strategy = None

        self.executed_sells = {}

        # Control flags
        self.running = False
        self.last_sell_check = datetime.now()

    async def discover_and_buy_tokens(self):
        """Discover new tokens and execute buy trades"""
        print("🔍 Discovering tokens to buy...")

        preset_name = "optimized_default"
        preset_params = TokenListPresets.optimized_default()
        print(f"  🎢 Using preset: {preset_name}")
        response = await fetch_token_list(preset_params)

        if not response.success or not response.items:
            print("  ⚠️ No tokens found")
            return

        # Apply volume/liquidity ratio filter (optimized default preset uses 1.5x-5x ratio)
        print(f"  📋 Found {len(response.items)} raw tokens from BirdEye")

        # Filter tokens by volume/liquidity ratio (1.5x-5x for optimized preset) and take top 10
        filtered = filter_by_volume_liquidity_ratio(response.items, min_ratio=1.5, max_ratio=5.0)[:10]

        print(f"  🔍 After volume/liquidity filtering: {len(filtered)} candidates")

        if not filtered:
            print("  ⚠️ No tokens available for analysis")
            return

        bought_count = 0
        for i, token in enumerate(filtered, 1):
            print(f"\n  📊 Processing token {i}/{len(filtered)}: {token.symbol}")
            # Skip if already own
            print(f"     🔍 Checking if we already own {token.symbol}...")
            balance = await check_token_balance(token.address, "solana")
            if balance > 0:
                print(f"     ⏭️ Already own {token.symbol} (balance: {balance})")
                continue

            # Skip if rejected
            print(f"     🔍 Checking rejection history for {token.symbol}...")
            if self.rejection_tracker.is_rejected(token.address, "solana"):
                print(f"     ⏭️ {token.symbol} previously rejected")
                continue

            # Fetch token data directly (no agency)
            print(f"     📊 Fetching data for {token.symbol}...")
            try:
                token_data = await fetch_all_token_data(token.address, "solana")

                if not token_data:
                    print(f"    ❌ No token data")
                    self.rejection_tracker.add_rejection(
                        token.address, "solana", "no_data", symbol=token.symbol
                    )
                    continue

                market = token_data.get("market_data", {})
                safety = token_data.get("safety_analysis", {})
                holder = token_data.get("holder_data", {})
                sentiment = token_data.get("sentiment_data", {})

                print(f"     💰 Price: ${market.get('price_usd', 0):.8f}")
                print(f"     💧 Liquidity: ${market.get('liquidity_usd', 0):,.0f}")
                print(f"     🔐 Risk: {safety.get('overall_risk', 'N/A')}")
                if holder:
                    print(f"     👥 Top10: {holder.get('top10_concentration', 0):.1f}%")
                if sentiment and sentiment.get("tweet_scout_score"):
                    print(f"     💭 TweetScout: {sentiment.get('tweet_scout_score'):.0f}")
                if sentiment and sentiment.get("grok_sentiment"):
                    grok_sent = sentiment.get("grok_sentiment")
                    grok_scam = sentiment.get("grok_scam_assessment")
                    print(f"     🤖 Grok: {grok_sent} | Scam Risk: {grok_scam}")

                print(f"    🔍 Evaluating Trading Criteria:")

                recommendation = self.trading_analyzer.analyze_structured_data(token_data)

                print(f"    📈 Decision: {recommendation.action} "
                      f"(confidence: {recommendation.confidence*100:.0f}%)")

                if recommendation.action == "BUY":
                    # Execute trade
                    if self.dry_run:
                        print(f"    🎭 DRY RUN: Would buy {token.symbol}")
                        bought_count += 1
                    else:
                        # Get SOL balance
                        sol_balance = get_sol_balance() or 0

                        # Calculate buy amount
                        max_amount = self.max_trade_amount or float(os.getenv("MAX_AMOUNT", "0.1"))
                        buy_amount = min(max_amount, sol_balance * 0.1)

                        # Reserve some SOL for transaction fees
                        fee_reserve = 0.005
                        min_required = buy_amount + fee_reserve

                        if sol_balance < min_required:
                            print(f"    ⚠️ Insufficient SOL: {sol_balance:.4f}")
                            continue

                        print(f"    💰 Buying with {buy_amount:.4f} SOL")

                        try:
                            swap_msg = f"BUY ${token.symbol} on Solana"
                            swap = AutoExecuteSwap(
                                message_content=swap_msg,
                                input_token="SOL",
                                token_address=token.address
                            )
                            result = swap.run()

                            # Check for success - result must exist and not contain ❌
                            result_stripped = result.strip() if result else ""
                            if result_stripped and "❌" not in result_stripped:
                                import re
                                tx_match = re.search(r'Transaction.*?`([A-Za-z0-9]+)`', result)
                                tx_hash = tx_match.group(1) if tx_match else "N/A"

                                print(f"    ✅ Successfully bought {token.symbol}")
                                if tx_hash != "N/A":
                                    print(f"    🔗 TX: {tx_hash}")
                                bought_count += 1
                            else:
                                error_msg = result if result else "Unknown error"
                                if "❌" in error_msg:
                                    parts = error_msg.split("❌")
                                    if len(parts) > 1:
                                        error_msg = parts[1].strip()
                                print(f"    ❌ Trade failed: {error_msg}")
                        except Exception as e:
                            print(f"    ❌ Trade error: {e}")
                else:
                    # Build rejection reason with failed criteria
                    failed_criteria = [
                        k for k, v in recommendation.criteria_met.items() if not v
                    ]
                    reason_data = json.dumps({
                        "action": recommendation.action,
                        "failed": failed_criteria,
                        "confidence": recommendation.confidence
                    })
                    print(f"    ❌ Rejected: {recommendation.action} "
                          f"(failed: {', '.join(failed_criteria)})")
                    self.rejection_tracker.add_rejection(
                        token.address,
                        "solana",
                        reason_data,
                        symbol=token.symbol
                    )

            except Exception as e:
                print(f"    ⚠️ Data fetch error: {e}")
                self.rejection_tracker.add_rejection(
                    token.address, "solana", "data_error", symbol=token.symbol
                )

        if bought_count > 0:
            print(f"\n  🛒 Bought {bought_count} new tokens")

    async def check_and_sell_positions(self):
        """Check positions and execute sells based on PnL"""
        if not self.enable_auto_sell or not self.sell_strategy:
            return

        now = datetime.now()
        if (now - self.last_sell_check).total_seconds() < self.sell_check_interval:
            return

        self.last_sell_check = now
        print("\n💹 Checking positions for auto-sell...")

        try:
            # Get wallet PnL
            wallet_address = os.getenv("DELEGATED_WALLET_ADDRESS")
            if not wallet_address:
                print("  ⚠️ No wallet address configured")
                return

            pnl_response = await fetch_wallet_pnl(wallet_address)

            if not pnl_response.tokens:
                print("  📭 No tokens to check")
                return

            sells_executed = 0

            for token in pnl_response.tokens:
                decision = self.sell_strategy.get_sell_decision(
                    unrealized_percent=token.unrealized_percent,
                    token_address=token.address,
                    current_price=token.current_price
                )

                if decision["sell_percentage"] > 0:
                    sell_pct = decision["sell_percentage"]

                    print(f"  🎯 {token.symbol}: {decision['action']} - "
                          f"{token.unrealized_percent:+.1f}% unrealized")
                    print(f"     Selling {sell_pct:.0f}% "
                          f"(${token.current_value * sell_pct / 100:.2f})")

                    if not self.dry_run:
                        # Execute sell
                        result = await execute_token_sell(token, sell_pct)

                        if result["success"]:
                            # Track the sell
                            if token.address not in self.executed_sells:
                                self.executed_sells[token.address] = []

                            self.executed_sells[token.address].append({
                                "timestamp": now.isoformat(),
                                "percentage": sell_pct,
                                "unrealized_percent": token.unrealized_percent,
                                "value_usd": token.current_value * sell_pct / 100
                            })

                            sells_executed += 1
                            print(f"     ✅ Sell executed successfully")
                        else:
                            if result.get("is_dead"):
                                print(f"     💀 Token appears dead: {result['error']}")
                            else:
                                print(f"     ❌ Sell failed: {result['error']}")
                    else:
                        print(f"     🎭 DRY RUN: Would sell {sell_pct:.0f}%")
                        sells_executed += 1

            if sells_executed > 0:
                print(f"  📊 Executed {sells_executed} sell orders")

        except Exception as e:
            print(f"  ❌ Error checking positions: {e}")

    async def run_cycle(self):
        """Run one complete trading cycle"""
        print(f"\n🤖 Trading Cycle - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        # Buy new tokens
        await self.discover_and_buy_tokens()

        # Check for sells
        await self.check_and_sell_positions()

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print current system status"""
        print("\n" + "=" * 60)
        print("📊 System Summary:")
        stats = self.rejection_tracker.get_stats()
        print(f"  Rejected Tokens: {stats['total_rejected']}")

        if self.enable_auto_sell and self.executed_sells:
            total_sells = sum(len(sells) for sells in self.executed_sells.values())
            print(f"  Sells Executed: {total_sells}")

        print("=" * 60)

    async def run(self, cycles: int = 1, interval_minutes: int = 5):
        """
        Run the trading system

        Args:
            cycles: Number of cycles to run (999 for continuous)
            interval_minutes: Minutes between cycles
        """
        self.running = True

        # Print configuration
        print("🚀 Starting Comprehensive Trading System")
        print(f"  Mode: {'DRY RUN' if self.dry_run else '⚠️ LIVE TRADING'}")

        criteria_class = self.trading_analyzer.criteria
        if criteria_class.max_overall_risk == RiskLevel.LOW and criteria_class.min_sentiment_score == 100.0:
            if criteria_class.max_concentration == ConcentrationLevel.HIGH:
                risk_name = "STRICT (Recommended Default)"
            elif criteria_class.max_concentration == ConcentrationLevel.LOW:
                risk_name = "CONSERVATIVE"
            else:
                risk_name = "MODERATE"
        elif criteria_class.max_overall_risk == RiskLevel.HIGH:
            risk_name = "AGGRESSIVE"
        else:
            risk_name = "CUSTOM"

        print(f"  Risk Profile: {risk_name}")
        print(f"  Auto-Sell: {'Enabled' if self.enable_auto_sell else 'Disabled'}")

        if self.enable_auto_sell:
            print(f"  Sell Check Interval: {self.sell_check_interval}s")
            print(f"  Stop Loss: {self.sell_strategy.loss_threshold}%")
            print(f"  Profit Tiers:")
            for profit_pct, sell_pct in self.sell_strategy.profit_tiers:
                multiplier = 1 + (profit_pct / 100)
                print(f"    {multiplier:.1f}x (+{profit_pct}%) → Sell {sell_pct}%")

        print(f"  Cycles: {'Continuous' if cycles == 0 else cycles}")
        print(f"  Interval: {interval_minutes} minutes")
        print("=" * 60)

        cycle_count = 0

        try:
            # cycles=0 means run indefinitely
            while self.running and (cycles == 0 or cycle_count < cycles):
                cycle_count += 1

                # Run trading cycle
                await self.run_cycle()

                # Check if we should continue (cycles=0 means infinite, so always sleep)
                should_continue = cycles == 0 or cycle_count < cycles
                if should_continue:
                    # If auto-sell is enabled, check more frequently
                    if self.enable_auto_sell:
                        # Sleep in smaller intervals to allow sell checks
                        total_sleep = interval_minutes * 60
                        sleep_interval = min(self.sell_check_interval, total_sleep)
                        sleep_remaining = total_sleep

                        while sleep_remaining > 0 and self.running:
                            await asyncio.sleep(min(sleep_interval, sleep_remaining))
                            sleep_remaining -= sleep_interval

                            # Check for sells during wait
                            if sleep_remaining > 0:
                                await self.check_and_sell_positions()
                    else:
                        # Simple sleep
                        print(f"\n⏰ Next cycle in {interval_minutes} minutes...")
                        await asyncio.sleep(interval_minutes * 60)

        except KeyboardInterrupt:
            print("\n⛔ Stopped by user")
        except asyncio.CancelledError:
            print("\n⛔ Trading system cancelled")
            raise  # Re-raise so the caller knows it was cancelled
        finally:
            self.running = False
            print("\n🛑 Trading system stopped")
            self.print_summary()


async def test_sell_strategy(args):
    """Test the sell strategy on current wallet holdings with optional execution"""
    live_mode = args.live if hasattr(args, 'live') else False
    mode_text = "🔥 LIVE EXECUTION" if live_mode else "🧪 SIMULATION ONLY"

    print(f"🧪 Testing Sell Strategy on Current Holdings ({mode_text})")
    print("=" * 60)

    # Parse profit tiers
    profit_tiers = parse_profit_tiers(args.profit_tiers) if args.profit_tiers else None

    # Initialize sell strategy
    sell_strategy = EnhancedProgressiveSellStrategy(
        loss_threshold=args.loss_threshold,
        profit_tiers=profit_tiers
    )

    # Display strategy configuration
    print(f"📋 Strategy Configuration:")
    print(f"  Stop Loss: {sell_strategy.loss_threshold}%")
    print(f"  Profit Tiers:")
    for profit_pct, sell_pct in sell_strategy.profit_tiers:
        multiplier = 1 + (profit_pct / 100)
        print(f"    {multiplier:.1f}x (+{profit_pct}%) → Sell {sell_pct}%")
    print(f"  Execution Mode: {'🔥 LIVE TRADES' if live_mode else '🧪 SIMULATION'}")

    if live_mode:
        print(f"⚠️  WARNING: Live mode will execute REAL sells on your tokens!")
        print(f"   Press Ctrl+C now to cancel, or wait 5 seconds to proceed...")
        try:
            import asyncio
            await asyncio.sleep(5)
            print(f"✅ Proceeding with live sell testing...")
        except KeyboardInterrupt:
            print(f"\n❌ Cancelled by user")
            return
    print()

    wallet_address = os.getenv("DELEGATED_WALLET_ADDRESS")
    if not wallet_address:
        print("❌ DELEGATED_WALLET_ADDRESS not configured")
        return

    try:
        print(f"📊 Fetching current holdings for {wallet_address[:8]}...")
        pnl_response = await fetch_wallet_pnl(wallet_address)

        if not pnl_response.tokens:
            print("📭 No token holdings found")
            return

        print(f"✅ Found {len(pnl_response.tokens)} token holdings")
        print()

        # Test sell strategy on each token
        total_recommendations = 0
        total_sell_value = 0.0
        executed_sells = 0

        for token in pnl_response.tokens:
            decision = sell_strategy.get_sell_decision(
                unrealized_percent=token.unrealized_percent,
                token_address=token.address,
                current_price=token.current_price
            )

            print(f"🪙 {token.symbol}")
            print(f"  Current Value: ${token.current_value:.2f}")
            print(f"  Unrealized PnL: {token.unrealized_percent:+.1f}% (${token.unrealized_usd:+.2f})")

            if decision["sell_percentage"] > 0:
                sell_amount_usd = token.current_value * decision["sell_percentage"] / 100
                total_sell_value += sell_amount_usd
                total_recommendations += 1

                print(f"  💡 Recommendation: {decision['action']}")
                print(f"  📤 Sell {decision['sell_percentage']:.0f}% → ${sell_amount_usd:.2f}")
                print(f"  💭 Reason: {decision['reason']}")

                if live_mode:
                    print(f"  🔥 Executing LIVE sell...")
                    try:
                        result = await execute_token_sell(token, decision["sell_percentage"])

                        if result["success"]:
                            executed_sells += 1
                            print(f"  ✅ Sell executed successfully!")
                            if result.get("tx_hash"):
                                print(f"  🔗 Transaction: {result['tx_hash']}")
                        else:
                            if result.get("is_dead"):
                                print(f"  💀 Token appears dead: {result.get('error', 'No liquidity')}")
                                print(f"     This token cannot be sold - no active market exists")
                            else:
                                error_msg = result.get('error', 'Unknown error')
                                if "slippage" in error_msg.lower() or "0x1771" in error_msg or "6001" in error_msg:
                                    print(f"  ⚠️  Slippage exceeded: Price moved too much during swap")
                                elif "invalid base58" in error_msg.lower():
                                    print(f"  ⚠️  Transaction error: Failed to sign/submit transaction")
                                elif "transaction too large" in error_msg.lower():
                                    print(f"  ⚠️  Transaction too complex: Try selling a smaller amount")
                                elif "insufficient" in error_msg.lower():
                                    print(f"  ❌ Sell failed: {error_msg}")
                                else:
                                    print(f"  ❌ Sell failed: {error_msg}")
                    except Exception as e:
                        print(f"  ❌ Sell error: {e}")
            else:
                print(f"  ✋ Hold - No sell signal")

            print()

        print("=" * 60)
        print("📊 Test Summary:")
        print(f"  Total Holdings: {len(pnl_response.tokens)} tokens")
        print(f"  Sell Recommendations: {total_recommendations}")
        print(f"  Total Sell Value: ${total_sell_value:.2f}")
        print(f"  Portfolio Value: ${pnl_response.total_current_value:.2f}")

        if live_mode:
            print(f"  🔥 Executed Sells: {executed_sells}/{total_recommendations}")
            if executed_sells > 0:
                print(f"  ✅ Successfully executed {executed_sells} sell order(s)")

        if total_recommendations > 0:
            sell_percentage = (total_sell_value / pnl_response.total_current_value) * 100
            if live_mode:
                print(f"  📈 Sold: {sell_percentage:.1f}% of portfolio")
            else:
                print(f"  Would Sell: {sell_percentage:.1f}% of portfolio")
        else:
            print("  🚫 No sells recommended at current prices")

        print()
        if live_mode:
            print("🔥 Live mode: Real trades were executed on your tokens!")
            if executed_sells > 0:
                print("   Check your wallet to confirm the completed transactions")
            else:
                print("   No sells were executed (no triggers met)")
        else:
            print("💡 This was a simulation - no actual trades were executed")
            print("   Use --test-sell --live to execute real sells")

    except Exception as e:
        print(f"❌ Error testing sell strategy: {e}")


def parse_profit_tiers(tiers_str: str) -> list:
    """Parse profit tiers from command line string"""
    if not tiers_str:
        return None

    try:
        tiers = []
        for tier in tiers_str.split(','):
            profit_str, sell_str = tier.strip().split(':')
            tiers.append((float(profit_str), float(sell_str)))
        return tiers
    except Exception as e:
        print(f"❌ Error parsing profit tiers: {e}")
        print("   Format: profit1:sell1,profit2:sell2,...")
        print("   Example: 50:20,100:50,200:20,900:10")
        sys.exit(1)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Comprehensive Trading System - Complete automated trading with buying and selling"
    )

    # Trading mode
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable LIVE trading (real money)"
    )

    # Risk profile
    parser.add_argument(
        "--risk",
        choices=["strict", "conservative", "moderate", "aggressive"],
        default="strict",
        help="Risk profile for trading decisions (default: strict - safest with TweetScout requirement)"
    )

    # Cycles and timing
    parser.add_argument(
        "--cycles",
        type=int,
        default=1,
        help="Number of cycles to run (0 for continuous/infinite, default: 1)"
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=3,
        help="Minutes between cycles (default: 3)"
    )

    # Auto-sell configuration
    parser.add_argument(
        "--auto-sell",
        action="store_true",
        help="Enable automatic selling based on PnL"
    )

    parser.add_argument(
        "--test-sell",
        action="store_true",
        help="Test sell strategy on current holdings without executing trades"
    )

    parser.add_argument(
        "--sell-interval",
        type=int,
        default=30,
        help="Seconds between sell checks when auto-sell is enabled (default: 30)"
    )

    parser.add_argument(
        "--loss-threshold",
        type=float,
        default=-10.0,
        help="Hard stop loss percentage (default: -10.0)"
    )

    parser.add_argument(
        "--profit-tiers",
        type=str,
        default=None,
        help="Custom profit tiers: profit1:sell1,profit2:sell2,... "
             "(default: 30:30,100:30,200:25,900:15)"
    )

    parser.add_argument(
        "--max-amount",
        type=float,
        default=None,
        help="Maximum amount in SOL per trade (e.g., 0.01 for max 0.01 SOL). "
             "Overrides MAX_AMOUNT env var (default: 0.1 SOL)"
    )

    args = parser.parse_args()

    if args.test_sell:
        await test_sell_strategy(args)
        return

    profit_tiers = parse_profit_tiers(args.profit_tiers) if args.profit_tiers else None

    system = ComprehensiveTradingSystem(
        dry_run=not args.live,
        risk_profile=args.risk,
        enable_auto_sell=args.auto_sell,
        sell_check_interval=args.sell_interval,
        loss_threshold=args.loss_threshold,
        profit_tiers=profit_tiers,
        max_trade_amount=args.max_amount
    )

    def signal_handler(signum, frame):
        system.running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    await system.run(args.cycles, args.interval)


if __name__ == "__main__":
    asyncio.run(main())
