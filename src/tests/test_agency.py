#!/usr/bin/env python3
"""
Test script for the GoArlo Crypto Summary Bot
Tests the complete workflow including data fetching and agency processing
"""

import asyncio
import argparse
import os
import sys
from dotenv import load_dotenv

# Add parent directory (src) to path to import main
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from main import analyze_token, holder_icon

load_dotenv()


async def test_sample_tokens():
    """Test with predefined sample tokens"""

    sample_tokens = [
        {
            "symbol": "SOL",
            "address": "So11111111111111111111111111111111111111112",
            "chain": "solana",
        },
        {
            "symbol": "USDC",
            "address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
            "chain": "base",
        },
    ]

    for token in sample_tokens:
        print(f"\n{'='*60}")
        print(f"Testing {token['symbol']} on {token['chain']}")
        print(f"Address: {token['address']}")
        print(f"{'='*60}")

        try:
            result = await analyze_token(
                token_address=token["address"],
                chain=token["chain"],
                token_symbol=token["symbol"],
            )

            if result["success"]:
                print("\n✅ Analysis Complete!")
                data = result["data"]
                token_info = data['token_info']
                print(f"Token: {token_info['name']} (${token_info['symbol']})")
                print(f"Chain: {token_info['chain']}")
                print(f"Address: {token_info['address']}")
                print(f"\nAnalysis Response: {data['analysis_response']}")
            else:
                print(f"\n❌ Analysis Failed: {result['error']}")

        except Exception as e:
            print(f"\n❌ Error analyzing {token['symbol']}: {str(e)}")


async def test_single_token(token_address: str, chain: str = None, symbol: str = None):
    """Test with a single token"""

    print(f"\n{'='*60}")
    print(f"Testing token on {chain or 'auto-detected chain'}")
    print(f"Address: {token_address}")
    print(f"{'='*60}")

    try:
        result = await analyze_token(
            token_address=token_address, chain=chain, token_symbol=symbol
        )

        if result["success"]:
            print("\n✅ Analysis Complete!")
            data = result["data"]
            token_info = data["token_info"]
            print(f"\n💠 **Token:** ${token_info['symbol']} 🌐 **Chain:** {token_info['chain'].title()}")
            print(f"🔗 {token_info['address']}")

            market = data["market_data"]
            print("\n📊 Market Data:")
            print(f"  💰 Price: ${market['price_usd']}")
            print(f"  🧮 FDV: ${market['fdv_usd']:,.0f}")
            print(f"  💧 Liquidity: ${market['liquidity_usd']:,.0f}")
            print(f"  🔁 24h Volume: ${market['volume_24h_usd']:,.0f}")

            if data["holder_data"]:
                holder = data["holder_data"]
                print("\n👥 Holder Data:")
                print(f"  Total Holders: {holder['total_holders']:,}")
                if holder.get("top10_concentration"):
                    concentration = holder['top10_concentration']
                    icon = holder_icon(concentration)
                    print(f"  Top 10 Concentration: {concentration:.1f}% {icon}")

            # Display bundler analysis if available (Solana only)
            if data.get("bundler_analysis"):
                bundler = data["bundler_analysis"]
                print("\n🔍 Bundler Analysis:")
                if bundler.get('bundled_detected'):
                    bundled_pct = bundler.get('bundled_transaction_percentage', 0)
                    if bundled_pct > 0:
                        print(f"  ⚠️ EARLY BUNDLES DETECTED: {bundled_pct:.1f}% (first 300 txs)")
                    current_risk = bundler.get('present_impact_analysis', {}).get('current_impact_risk', 'N/A')
                    print(f"  🧨 Current Impact Risk: {current_risk}")
                else:
                    print(f"  ✅ NO BUNDLES DETECTED")
                    print(f"  🧨 Current Impact Risk: LOW")

            # Display 24h market health if available
            if data.get("market_health_24h"):
                health = data["market_health_24h"]
                print("\n📈 24h Market Health:")
                print(f"  Overall Health: {health.get('market_health', 'N/A')}")

                buy_pct = health.get('buy_pressure_pct', 'N/A')
                sell_pct = health.get('sell_pressure_pct', 'N/A')
                pressure_dominance = health.get('pressure_dominance', 'N/A')
                if buy_pct != 'N/A' and sell_pct != 'N/A':
                    print(f"  Buy/Sell Pressure: {buy_pct:.1f}% / {sell_pct:.1f}% ({pressure_dominance})")
                else:
                    print(f"  Buy/Sell Pressure: {buy_pct} / {sell_pct} ({pressure_dominance})")

                vol_change = health.get('volume_change_pct', 'N/A')
                if vol_change != 'N/A':
                    print(f"  Volume Change: {vol_change:+.1f}%")
                else:
                    print(f"  Volume Change: {vol_change}")

                volatility = health.get('avg_volatility_pct', 'N/A')
                if volatility != 'N/A':
                    print(f"  Volatility: {volatility:.1f}%")
                else:
                    print(f"  Volatility: {volatility}")

            # Display token safety analysis if available
            if data.get("safety_analysis"):
                safety = data["safety_analysis"]
                print("\n🔒 Token Safety Analysis:")
                print(f"  Overall Risk: {safety.get('overall_risk', 'N/A')}")

                contract_control = safety.get('contract_control', {})
                status_emoji = "✅" if contract_control.get('status') == 'positive' else "⚠️" if contract_control.get('status') == 'neutral' else "❌"
                print(f"  Contract Control: {status_emoji} {contract_control.get('status', 'unknown').upper()}")
                print(f"    {contract_control.get('reason', 'No data available')}")

                holder_control = safety.get('holder_control', {})
                status_emoji = "✅" if holder_control.get('status') == 'positive' else "⚠️" if holder_control.get('status') == 'neutral' else "❌"
                print(f"  Holder Control: {status_emoji} {holder_control.get('status', 'unknown').upper()}")
                print(f"    {holder_control.get('reason', 'No data available')}")

                # Display chain-specific data
                if token_info.get('chain', '').lower() == 'solana':
                    key_metrics = safety.get('key_metrics', {})
                    if key_metrics.get('jupiter_strict_list'):
                        print(f"  Jupiter Strict List: ✅ VERIFIED")
                    if key_metrics.get('mutable_metadata'):
                        print(f"  Metadata: 🔄 MUTABLE")
                else:
                    security_checks = safety.get('security_checks', {})
                    if security_checks:
                        status_emoji = "✅" if security_checks.get('status') == 'positive' else "⚠️" if security_checks.get('status') == 'neutral' else "❌"
                        print(f"  Security Checks: {status_emoji} {security_checks.get('status', 'unknown').upper()}")
                        print(f"    {security_checks.get('reason', 'No data available')}")

                    liquidity_analysis = safety.get('liquidity_analysis', {})
                    if liquidity_analysis:
                        status_emoji = "✅" if liquidity_analysis.get('status') == 'positive' else "⚠️" if liquidity_analysis.get('status') == 'neutral' else "❌"
                        print(f"  Liquidity Analysis: {status_emoji} {liquidity_analysis.get('status', 'unknown').upper()}")
                        print(f"    {liquidity_analysis.get('reason', 'No data available')}")

            print(f"\n{data['analysis_response']}")
        else:
            print(f"\n❌ Analysis Failed: {result['error']}")

    except Exception as e:
        print(f"\n❌ Error analyzing token: {str(e)}")


def check_environment():
    """Check if required environment variables are set"""

    required_vars = ["OPENAI_API_KEY", "XAI_API_KEY"]
    optional_vars = ["TWEET_SCOUT_ID", "MORALIS_API_KEY"]

    print("🔧 Environment Check:")
    print("-" * 25)

    all_required_set = True
    for var in required_vars:
        if os.getenv(var):
            print(f"✅ {var}")
        else:
            print(f"❌ {var} (Required)")
            all_required_set = False

    for var in optional_vars:
        if os.getenv(var):
            print(f"✅ {var}")
        else:
            print(f"⚠️  {var} (Optional)")

    if not all_required_set:
        print("\n❌ Missing required environment variables")
        return False

    print("✅ Environment check passed")
    return True


async def main():
    parser = argparse.ArgumentParser(
        description="Test GoArlo Crypto Summary Bot - Complete Workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_agency.py --address So11111111111111111111111111111111111111112 --symbol SOL
  python test_agency.py --address 0x1234... --chain ethereum --symbol ETH
  python test_agency.py --samples
        """,
    )

    parser.add_argument("--address", help="Token contract address")
    parser.add_argument(
        "--chain", help="Blockchain (solana, ethereum, base, bnb, shibarium)"
    )
    parser.add_argument("--symbol", help="Token symbol (auto-detected if not provided)")
    parser.add_argument(
        "--samples", action="store_true", help="Test with sample tokens"
    )

    args = parser.parse_args()

    print("🚀 GoArlo Crypto Summary Bot - Test Suite")
    print("=" * 50)

    # Check environment
    if not check_environment():
        return

    try:
        if args.address:
            # Test single token
            await test_single_token(args.address, args.chain, args.symbol)

        elif args.samples:
            # Test sample tokens
            await test_sample_tokens()

        else:
            print("\nUsage Options:")
            print("1. Test single token:")
            print(
                "   python test_agency.py --address <ADDRESS> [--chain <CHAIN>] [--symbol <SYMBOL>]"
            )
            print("\n2. Test sample tokens:")
            print("   python test_agency.py --samples")
            print("\n3. Complete workflow:")
            print("   python main.py --address <ADDRESS>")

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
