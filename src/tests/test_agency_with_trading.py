#!/usr/bin/env python3
"""
Test script for the complete GoArlo Agency flow including trading decisions and execution.
Tests the complete workflow from data fetching through agency processing to trade execution.
"""

import asyncio
import argparse
import os
import sys
import json
from dotenv import load_dotenv
from typing import Dict, Any

# Add parent directory (src) to path to import modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import main for data fetching
from main import analyze_token, holder_icon

# Import trading agent tools for trading decisions and execution
sys.path.append(os.path.join(parent_dir, "trading_agent"))
from tools.MakeTradingDecision import MakeTradingDecision
from tools.CalculatePositionSize import CalculatePositionSize
from tools.AutoExecuteSwap import AutoExecuteSwap

load_dotenv()


def format_narrative_for_trading(data: Dict[str, Any]) -> str:
    """
    Format the data fetched by main.py into a comprehensive narrative
    suitable for the trading agent's MakeTradingDecision tool.
    """
    token_info = data.get("token_info", {})
    market_data = data.get("market_data", {})
    holder_data = data.get("holder_data", {})
    bundler_analysis = data.get("bundler_analysis", {})
    market_health = data.get("market_health_24h", {})
    safety_analysis = data.get("safety_analysis", {})

    # Start building the narrative
    narrative = f"""
Token: {token_info.get('name', 'Unknown')} ({token_info.get('symbol', 'N/A')})
Chain: {token_info.get('chain', 'Unknown')}
Address: {token_info.get('address', 'N/A')}
Price: ${market_data.get('price_usd', 'N/A')}
FDV: ${market_data.get('fdv_usd', 'N/A')}
Market Cap: ${market_data.get('market_cap_usd', 'N/A')}
24h Volume: ${market_data.get('volume_24h_usd', 'N/A')}
Liquidity: ${market_data.get('liquidity_usd', 'N/A')}
"""

    if holder_data:
        narrative += f"""Total Holders: {holder_data.get('total_holders', 'N/A')}
Top 10 Concentration: {holder_data.get('top10_concentration', 'N/A')}%
"""

    # Add narrative sections (simulated from grok narration agent)
    narrative += """
### Market Overview
"""
    if market_health:
        vol_change = market_health.get('volume_change_pct', 0)
        buy_pressure = market_health.get('buy_pressure_pct', 50)
        sell_pressure = market_health.get('sell_pressure_pct', 50)
        volatility = market_health.get('avg_volatility_pct', 5)

        if vol_change > 0:
            narrative += f"Volume up {vol_change:.1f}% signals increasing interest. "
        else:
            narrative += f"Volume down {abs(vol_change):.1f}% suggests declining momentum. "

        narrative += f"Buy/sell pressure at {buy_pressure:.0f}%/{sell_pressure:.0f}% "

        if buy_pressure > sell_pressure:
            narrative += "shows bullish sentiment. "
        elif sell_pressure > buy_pressure:
            narrative += "indicates selling pressure. "
        else:
            narrative += "remains balanced. "

        narrative += f"Volatility at {volatility:.1f}% "
        if volatility < 5:
            narrative += "provides stable entry conditions."
        else:
            narrative += "suggests cautious positioning."
    else:
        narrative += "Limited market data available for analysis."

    narrative += """

### Token Safety
"""
    if safety_analysis:
        contract_control = safety_analysis.get('contract_control', {})
        holder_control = safety_analysis.get('holder_control', {})

        if contract_control.get('status') == 'positive':
            narrative += f"Contract control: {contract_control.get('reason', 'Positive safety profile')}. "
        elif contract_control.get('status') == 'negative':
            narrative += f"Contract control warning: {contract_control.get('reason', 'Risk detected')}. "

        if holder_control.get('status') == 'positive':
            narrative += f"Holder restrictions: {holder_control.get('reason', 'No restrictions detected')}. "
        elif holder_control.get('status') == 'negative':
            narrative += f"Holder restriction warning: {holder_control.get('reason', 'Restrictions present')}. "

        overall_risk = safety_analysis.get('overall_risk', 'UNKNOWN')
        narrative += f"Overall: {overall_risk} safety risk level."
    else:
        narrative += "Safety analysis data not available."

    narrative += """

### Holder Insights
"""
    if holder_data:
        holders = holder_data.get('total_holders', 0)
        concentration = holder_data.get('top10_concentration', 0)

        if holders > 0:
            narrative += f"{holders:,} holders "

        if concentration > 0:
            if concentration > 30:
                narrative += f"with high {concentration:.1f}% top-10 concentration creates whale risk. "
            elif concentration > 20:
                narrative += f"with moderate {concentration:.1f}% top-10 concentration requires monitoring. "
            else:
                narrative += f"with healthy {concentration:.1f}% top-10 concentration shows good distribution. "

        narrative += "Monitor for holder pattern changes."
    else:
        narrative += "Holder data unavailable for this token."

    narrative += """

### Risk Assessment
"""
    # Solana-specific bundling risk
    if token_info.get('chain', '').lower() == 'solana' and bundler_analysis:
        if bundler_analysis.get('bundled_detected'):
            current_risk = bundler_analysis.get('present_impact_analysis', {}).get('current_impact_risk', 'UNKNOWN')
            narrative += f"{current_risk} bundling risk detected. "
        else:
            narrative += "LOW bundling risk with organic launch pattern. "

    # Market health assessment
    if market_health:
        health_rating = market_health.get('market_health', 'UNKNOWN')
        narrative += f"{health_rating} 24h market health "

        if health_rating in ['EXCELLENT', 'GOOD']:
            narrative += "supports positive outlook. "
        elif health_rating == 'FAIR':
            narrative += "suggests cautious approach. "
        else:
            narrative += "indicates elevated risk. "

    # Holder concentration risk
    if holder_data and holder_data.get('top10_concentration', 0) > 20:
        narrative += "Whale concentration adds manipulation risk. "

    narrative += "Overall: Assess risk tolerance before entry."

    narrative += """

### Social & Trends
"""
    # Simulated sentiment (in real implementation, this would come from sentiment analysis)
    sentiment_data = data.get('sentiment_analysis', {})
    if sentiment_data:
        sentiment = sentiment_data.get('label', 'Neutral')
        narrative += f"{sentiment} sentiment detected. "
    else:
        narrative += "Neutral sentiment assumed without social data. "

    narrative += "Monitor community engagement for trend changes."

    # Add market health data
    if market_health:
        narrative += f"""

24H MARKET HEALTH:
- Overall Health: {market_health.get('market_health', 'N/A')}
- Pressure Dominance: {market_health.get('pressure_dominance', 'N/A')}
- Buy/Sell Pressure: {market_health.get('buy_pressure_pct', 'N/A')}% / {market_health.get('sell_pressure_pct', 'N/A')}%
- Volume Change: {market_health.get('volume_change_pct', 'N/A')}%
- Avg Volatility: {market_health.get('avg_volatility_pct', 'N/A')}%
"""

    # Add safety analysis data
    if safety_analysis:
        narrative += f"""

TOKEN SAFETY ANALYSIS:
- Overall Risk Level: {safety_analysis.get('overall_risk', 'N/A')}
"""
        if safety_analysis.get('contract_control'):
            cc = safety_analysis['contract_control']
            narrative += f"- Contract Control: {cc.get('status', 'N/A').upper()} - {cc.get('reason', 'N/A')}\n"
        if safety_analysis.get('holder_control'):
            hc = safety_analysis['holder_control']
            narrative += f"- Holder Control: {hc.get('status', 'N/A').upper()} - {hc.get('reason', 'N/A')}\n"

    return narrative


async def test_complete_agency_flow(token_address: str, chain: str = None, symbol: str = None, execute_trade: bool = False):
    """
    Test the complete agency flow from data fetching to trading decision and potential execution.
    """
    print(f"\n{'='*80}")
    print("🚀 COMPLETE AGENCY FLOW TEST")
    print(f"{'='*80}")
    print(f"Token: {symbol or 'Auto-detect'}")
    print(f"Chain: {chain or 'Auto-detect'}")
    print(f"Address: {token_address}")
    print(f"Trade Execution: {'ENABLED ⚠️' if execute_trade else 'DISABLED (Simulation Only)'}")
    print(f"{'='*80}\n")

    try:
        # Step 1: Fetch comprehensive data
        print("📊 Step 1: Fetching Comprehensive Token Data...")
        print("-" * 40)

        result = await analyze_token(
            token_address=token_address,
            chain=chain,
            token_symbol=symbol
        )

        if not result["success"]:
            print(f"❌ Data fetching failed: {result['error']}")
            return

        data = result["data"]
        token_info = data["token_info"]

        print(f"✅ Data fetched for {token_info['symbol']} on {token_info['chain']}")
        print(f"   Price: ${data['market_data']['price_usd']}")
        print(f"   24h Volume: ${data['market_data']['volume_24h_usd']}")
        print(f"   Liquidity: ${data['market_data']['liquidity_usd']}")

        # Step 2: Generate comprehensive narrative (simulating grok narration agent)
        print(f"\n📝 Step 2: Generating Comprehensive Narrative...")
        print("-" * 40)

        narrative = format_narrative_for_trading(data)
        print("✅ Narrative generated with market overview, safety, holder insights, and risk assessment")

        # Step 3: Make trading decision
        print(f"\n🎯 Step 3: Making Trading Decision...")
        print("-" * 40)

        decision_tool = MakeTradingDecision(message_content=narrative)
        decision_result = decision_tool.run()

        print(decision_result)

        # Extract decision data from the result
        # Parse the decision from the formatted output
        recommendation = "HOLD"
        confidence = "MEDIUM"
        score = 50

        if "**BUY**" in decision_result:
            recommendation = "BUY"
        elif "**SELL**" in decision_result:
            recommendation = "SELL"
        elif "**AVOID**" in decision_result:
            recommendation = "AVOID"

        if "**HIGH" in decision_result:
            confidence = "HIGH"
        elif "**LOW" in decision_result:
            confidence = "LOW"

        # Try to extract score
        try:
            if "Trading Score:" in decision_result:
                score_line = [line for line in decision_result.split('\n') if 'Trading Score:' in line][0]
                score = int(score_line.split(':')[1].split('/')[0].strip().replace('*', ''))
        except:
            pass

        # Create decision dictionary
        trading_decision = {
            "recommendation": recommendation,
            "confidence": confidence,
            "score": score,
            "risk_score": 100 - score,
            "position_size": "SMALL" if score < 70 else "MEDIUM" if score < 85 else "LARGE",
            "token_address": token_info.get('address'),
            "token_symbol": token_info.get('symbol'),
            "chain": token_info.get('chain', '').upper()
        }

        print(f"\n📊 Decision Summary:")
        print(f"   Recommendation: {trading_decision['recommendation']}")
        print(f"   Confidence: {trading_decision['confidence']}")
        print(f"   Score: {trading_decision['score']}/100")
        print(f"   Chain: {trading_decision['chain']}")

        # Step 4: Check if auto-execution is possible
        is_solana = trading_decision['chain'] == 'SOLANA'
        is_buy = trading_decision['recommendation'] == 'BUY'
        is_qualified = (
            trading_decision['confidence'] in ['HIGH', 'MEDIUM'] and
            trading_decision['score'] >= 60 and
            trading_decision['risk_score'] <= 80
        )

        if is_buy:
            if is_solana and is_qualified:
                print(f"\n✅ AUTO-EXECUTION AVAILABLE (Solana + Qualified BUY Signal)")

                # Step 5: Calculate position size (Solana only)
                print(f"\n💰 Step 4: Calculating Position Size...")
                print("-" * 40)

                position_tool = CalculatePositionSize(
                    trading_decision=trading_decision,
                    token_address=token_info['address'],
                    token_symbol=token_info['symbol']
                )

                position_result = position_tool.run()
                print(position_result)

                # Step 6: Execute trade if enabled
                if execute_trade:
                    print(f"\n🚀 Step 5: EXECUTING TRADE...")
                    print("-" * 40)
                    print("⚠️  REAL MONEY TRANSACTION - EXECUTING SWAP ON SOLANA")

                    auto_execute_tool = AutoExecuteSwap(
                        trading_decision=trading_decision,
                        token_address=token_info['address'],
                        token_symbol=token_info['symbol'],
                        custom_slippage=1.0
                    )

                    execution_result = auto_execute_tool.run()
                    print(execution_result)
                else:
                    print(f"\n⚠️  Step 5: Trade Execution SKIPPED (Simulation Mode)")
                    print("-" * 40)
                    print("To enable real execution, use --execute flag")
                    print("WARNING: This will execute real trades with your wallet!")

            elif not is_solana:
                print(f"\n⚠️  MANUAL EXECUTION REQUIRED ({trading_decision['chain']} chain)")
                print("   Auto-execution only available for Solana tokens")
                print("   Follow manual execution guidance in the trading decision")
            else:
                print(f"\n⚠️  BUY SIGNAL DOES NOT MEET AUTO-EXECUTION CRITERIA")
                print(f"   Confidence: {trading_decision['confidence']} (needs HIGH/MEDIUM)")
                print(f"   Score: {trading_decision['score']}/100 (needs ≥60)")
                print(f"   Risk Score: {trading_decision['risk_score']}/100 (needs ≤80)")
        else:
            print(f"\n📋 RECOMMENDATION: {trading_decision['recommendation']}")
            print("   No execution needed (not a BUY signal)")

        # Final summary
        print(f"\n{'='*80}")
        print("📈 AGENCY FLOW COMPLETE")
        print(f"{'='*80}")
        print(f"Token: {token_info['symbol']} on {token_info['chain']}")
        print(f"Decision: {trading_decision['recommendation']} with {trading_decision['confidence']} confidence")
        print(f"Score: {trading_decision['score']}/100")

        if is_buy and is_solana and is_qualified:
            print(f"Execution: {'✅ COMPLETED' if execute_trade else '⚠️ AVAILABLE BUT SKIPPED'}")
        elif is_buy and not is_solana:
            print(f"Execution: 📋 MANUAL REQUIRED ({trading_decision['chain']} chain)")
        else:
            print(f"Execution: ➖ NOT APPLICABLE")

    except Exception as e:
        print(f"\n❌ Error in agency flow: {str(e)}")
        import traceback
        traceback.print_exc()


async def test_sample_tokens_with_trading():
    """Test the agency flow with predefined sample tokens"""

    sample_tokens = [
        {
            "symbol": "WIF",
            "address": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
            "chain": "solana",
            "description": "Dogwifhat - Popular Solana meme token"
        },
        {
            "symbol": "PEPE",
            "address": "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
            "chain": "ethereum",
            "description": "Pepe - Popular Ethereum meme token"
        },
        {
            "symbol": "DEGEN",
            "address": "0x4ed4E862860beD51a9570b96d89aF5E1B0Eff574",
            "chain": "base",
            "description": "Degen - Base chain social token"
        }
    ]

    for token in sample_tokens:
        print(f"\n{'='*80}")
        print(f"Testing: {token['description']}")
        print(f"{'='*80}")

        await test_complete_agency_flow(
            token_address=token["address"],
            chain=token["chain"],
            symbol=token["symbol"],
            execute_trade=False  # Never auto-execute in sample mode
        )

        print("\n⏸️  Pausing before next token...")
        await asyncio.sleep(2)


def check_trading_environment():
    """Check if required environment variables for trading are set"""

    required_vars = ["OPENAI_API_KEY", "XAI_API_KEY"]
    trading_vars = [
        "DELEGATED_WALLET_ADDRESS",
        "TURNKEY_ORGANIZATION_ID",
        "TURNKEY_API_PUBLIC_KEY",
        "TURNKEY_API_PRIVATE_KEY",
        "MAX_AMOUNT"
    ]
    optional_vars = ["TWEET_SCOUT_ID", "MORALIS_API_KEY"]

    print("🔧 Environment Check:")
    print("-" * 40)

    all_required_set = True
    for var in required_vars:
        if os.getenv(var):
            print(f"✅ {var}")
        else:
            print(f"❌ {var} (Required)")
            all_required_set = False

    print("\n🏦 Trading Configuration:")
    trading_ready = True
    for var in trading_vars:
        if os.getenv(var):
            if var == "MAX_AMOUNT":
                print(f"✅ {var}: {os.getenv(var)} SOL")
            elif "PRIVATE_KEY" in var:
                print(f"✅ {var}: ***configured***")
            else:
                value = os.getenv(var)
                if len(value) > 20:
                    print(f"✅ {var}: {value[:8]}...{value[-4:]}")
                else:
                    print(f"✅ {var}: {value}")
        else:
            print(f"⚠️  {var} (Needed for auto-execution)")
            trading_ready = False

    print("\n📦 Optional APIs:")
    for var in optional_vars:
        if os.getenv(var):
            print(f"✅ {var}")
        else:
            print(f"⚠️  {var} (Optional)")

    if not all_required_set:
        print("\n❌ Missing required environment variables")
        return False

    if not trading_ready:
        print("\n⚠️  Trading execution not fully configured")
        print("   You can still test decisions but auto-execution will fail")
    else:
        print("\n✅ All systems ready for trading!")

    return all_required_set


async def main():
    parser = argparse.ArgumentParser(
        description="Test Complete GoArlo Agency Flow - From Analysis to Trade Execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test single Solana token (auto-execution available)
  python test_agency_with_trading.py --address EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm --symbol WIF --chain solana

  # Test with real execution (CAUTION: Real money!)
  python test_agency_with_trading.py --address EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm --symbol WIF --chain solana --execute

  # Test Ethereum token (manual execution only)
  python test_agency_with_trading.py --address 0x6982508145454Ce325dDbE47a25d4ec3d2311933 --symbol PEPE --chain ethereum

  # Test multiple sample tokens
  python test_agency_with_trading.py --samples
        """,
    )

    parser.add_argument("--address", help="Token contract address")
    parser.add_argument("--chain", help="Blockchain (solana, ethereum, base, bnb, polygon)")
    parser.add_argument("--symbol", help="Token symbol")
    parser.add_argument("--samples", action="store_true", help="Test with sample tokens")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="⚠️  ACTUALLY EXECUTE TRADES (real money!) - Only for Solana tokens"
    )

    args = parser.parse_args()

    print("🚀 GoArlo Complete Agency Flow Test")
    print("=" * 80)
    print("This test runs the entire pipeline:")
    print("1. Data Fetching (BirdEye, Moralis, etc.)")
    print("2. Narrative Generation (simulated)")
    print("3. Trading Decision (MakeTradingDecision)")
    print("4. Position Sizing (CalculatePositionSize)")
    print("5. Trade Execution (AutoExecuteSwap) - Solana only")
    print("=" * 80)

    # Check environment
    if not check_trading_environment():
        return

    if args.execute and not args.address:
        print("\n⚠️  --execute flag requires --address to be specified")
        print("   Cannot execute trades in sample mode")
        return

    try:
        if args.address:
            # Test single token
            await test_complete_agency_flow(
                args.address,
                args.chain,
                args.symbol,
                execute_trade=args.execute
            )

        elif args.samples:
            # Test sample tokens (never execute)
            await test_sample_tokens_with_trading()

        else:
            print("\n📋 Usage Options:")
            print("\n1. Test single token (simulation):")
            print("   python test_agency_with_trading.py --address <ADDRESS> --chain <CHAIN> --symbol <SYMBOL>")
            print("\n2. Test single token with REAL EXECUTION:")
            print("   python test_agency_with_trading.py --address <ADDRESS> --chain solana --symbol <SYMBOL> --execute")
            print("\n3. Test sample tokens:")
            print("   python test_agency_with_trading.py --samples")

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())