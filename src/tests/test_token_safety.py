#!/usr/bin/env python3
"""
Test script for the Token Safety Analysis module
Tests the BirdEye API integration and analysis logic
"""

import asyncio
import argparse
import os
import sys
from dotenv import load_dotenv

# Add parent directory (src) to path to import token_safety
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from token_safety import analyze_token_safety, TokenSafetyAnalyzer

load_dotenv()


async def test_sample_tokens():
    """Test with predefined sample tokens across different chains"""

    sample_tokens = [
        {
            "name": "Solana (SOL)",
            "address": "So11111111111111111111111111111111111111112",
            "chain": "solana",
        },
        {
            "name": "Base USDC",
            "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "chain": "base",
        },
        {
            "name": "Ethereum USDC",
            "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "chain": "ethereum",
        },
        {
            "name": "BSC Token",
            "address": "0x95AF4aF910c28E8EcE4512BFE46F1F33687424ce",
            "chain": "bsc",
        },
    ]

    for token in sample_tokens:
        print(f"\n{'='*70}")
        print(f"Testing {token['name']}")
        print(f"Address: {token['address']}")
        print(f"Chain: {token['chain']}")
        print(f"{'='*70}")

        try:
            result = await analyze_token_safety(token["address"], token["chain"])

            if result["success"]:
                print("✅ Safety Analysis Complete!")
                analysis = result["analysis"]

                print(f"\n🎯 Overall Risk: {analysis['overall_risk']}")

                # Contract Control
                contract = analysis.get('contract_control', {})
                status_emoji = "✅" if contract.get('status') == 'positive' else "⚠️" if contract.get('status') == 'neutral' else "❌"
                print(f"\n🏛️ Contract Control: {status_emoji} {contract.get('status', 'unknown').upper()}")
                print(f"   Reason: {contract.get('reason', 'No data')}")

                # Holder Control
                holder = analysis.get('holder_control', {})
                status_emoji = "✅" if holder.get('status') == 'positive' else "⚠️" if holder.get('status') == 'neutral' else "❌"
                print(f"\n👥 Holder Control: {status_emoji} {holder.get('status', 'unknown').upper()}")
                print(f"   Reason: {holder.get('reason', 'No data')}")

                # Chain-specific data
                if token['chain'] == 'solana':
                    key_metrics = analysis.get('key_metrics', {})
                    if key_metrics.get('jupiter_strict_list'):
                        print(f"\n⭐ Jupiter Strict List: ✅ VERIFIED")
                    if key_metrics.get('mutable_metadata'):
                        print(f"🔄 Metadata: MUTABLE")
                else:
                    # EVM chains
                    security = analysis.get('security_checks', {})
                    liquidity = analysis.get('liquidity_analysis', {})

                    if security:
                        status_emoji = "✅" if security.get('status') == 'positive' else "⚠️" if security.get('status') == 'neutral' else "❌"
                        print(f"\n🔒 Security: {status_emoji} {security.get('status', 'unknown').upper()}")
                        print(f"   {security.get('reason', 'No data')}")

                    if liquidity:
                        status_emoji = "✅" if liquidity.get('status') == 'positive' else "⚠️" if liquidity.get('status') == 'neutral' else "❌"
                        print(f"\n💧 Liquidity: {status_emoji} {liquidity.get('status', 'unknown').upper()}")
                        print(f"   {liquidity.get('reason', 'No data')}")

                # Key metrics
                key_metrics = analysis.get('key_metrics', {})
                if key_metrics:
                    print(f"\n📊 Key Metrics:")
                    for key, value in key_metrics.items():
                        if value is not None and value != 0:
                            print(f"   {key}: {value}")

            else:
                print(f"❌ Safety Analysis Failed: {result['error']}")

        except Exception as e:
            print(f"❌ Error analyzing {token['name']}: {str(e)}")


async def test_single_token(token_address: str, chain: str):
    """Test with a single token"""

    print(f"\n{'='*70}")
    print(f"Testing Token Safety Analysis")
    print(f"Address: {token_address}")
    print(f"Chain: {chain}")
    print(f"{'='*70}")

    try:
        result = await analyze_token_safety(token_address, chain)

        if result["success"]:
            print("✅ Safety Analysis Complete!")
            analysis = result["analysis"]

            print(f"\n🎯 Overall Risk Level: {analysis['overall_risk']}")

            # Contract Control
            contract = analysis.get('contract_control', {})
            print(f"\n🏛️ Contract Control:")
            print(f"   Status: {contract.get('status', 'unknown').upper()}")
            print(f"   Reason: {contract.get('reason', 'No data')}")
            print(f"   Risk: {contract.get('risk', 'Unknown risk')}")

            # Holder Control
            holder = analysis.get('holder_control', {})
            print(f"\n👥 Holder Control:")
            print(f"   Status: {holder.get('status', 'unknown').upper()}")
            print(f"   Reason: {holder.get('reason', 'No data')}")
            print(f"   Risk: {holder.get('risk', 'Unknown risk')}")

            # Chain-specific analysis
            if chain.lower() == 'solana':
                liquidity = analysis.get('liquidity_analysis', {})
                if liquidity:
                    print(f"\n💧 Liquidity Analysis:")
                    print(f"   Status: {liquidity.get('status', 'unknown').upper()}")
                    print(f"   Reason: {liquidity.get('reason', 'No data')}")
                    print(f"   Risk: {liquidity.get('risk', 'Unknown risk')}")
            else:
                # EVM chains
                security = analysis.get('security_checks', {})
                if security:
                    print(f"\n🔒 Security Checks:")
                    print(f"   Status: {security.get('status', 'unknown').upper()}")
                    print(f"   Reason: {security.get('reason', 'No data')}")
                    print(f"   Risk: {security.get('risk', 'Unknown risk')}")

                liquidity = analysis.get('liquidity_analysis', {})
                if liquidity:
                    print(f"\n💧 Liquidity Analysis:")
                    print(f"   Status: {liquidity.get('status', 'unknown').upper()}")
                    print(f"   Reason: {liquidity.get('reason', 'No data')}")
                    print(f"   Risk: {liquidity.get('risk', 'Unknown risk')}")

            # Key metrics
            key_metrics = analysis.get('key_metrics', {})
            if key_metrics:
                print(f"\n📊 Key Metrics:")
                for key, value in key_metrics.items():
                    print(f"   {key}: {value}")

            # Raw data (optional, for debugging)
            print(f"\n🔧 Raw Data Available: {'Yes' if result.get('raw_data') else 'No'}")

        else:
            print(f"❌ Safety Analysis Failed: {result['error']}")

    except Exception as e:
        print(f"❌ Error analyzing token: {str(e)}")


def check_environment():
    """Check if required environment variables are set"""

    required_vars = ["BIRDEYE_API_KEY"]

    print("🔧 Environment Check:")
    print("-" * 25)

    all_required_set = True
    for var in required_vars:
        if os.getenv(var):
            print(f"✅ {var}")
        else:
            print(f"❌ {var} (Required)")
            all_required_set = False

    if not all_required_set:
        print("\n❌ Missing required environment variables")
        print("Please check your .env file and ensure BIRDEYE_API_KEY is set")
        return False

    print("✅ Environment check passed")
    return True


async def test_analyzer_direct():
    """Test the TokenSafetyAnalyzer class directly"""

    print("\n🧪 Testing TokenSafetyAnalyzer Class")
    print("=" * 50)

    try:
        analyzer = TokenSafetyAnalyzer()
        print("✅ TokenSafetyAnalyzer initialized successfully")

        # Test with a known Solana token
        result = await analyzer.analyze_token_safety(
            "So11111111111111111111111111111111111111112",
            "solana"
        )

        if result["success"]:
            print("✅ Direct analyzer test passed")
            print(f"   Risk Level: {result['analysis']['overall_risk']}")
        else:
            print(f"❌ Direct analyzer test failed: {result['error']}")

    except Exception as e:
        print(f"❌ TokenSafetyAnalyzer test failed: {str(e)}")


async def main():
    parser = argparse.ArgumentParser(
        description="Test Token Safety Analysis Module",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_token_safety.py --address So11111111111111111111111111111111111111112 --chain solana
  python test_token_safety.py --address 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 --chain base
  python test_token_safety.py --samples
  python test_token_safety.py --test-analyzer
        """,
    )

    parser.add_argument("--address", help="Token contract address")
    parser.add_argument(
        "--chain", help="Blockchain (solana, ethereum, base, bsc, shibarium)"
    )
    parser.add_argument(
        "--samples", action="store_true", help="Test with sample tokens"
    )
    parser.add_argument(
        "--test-analyzer", action="store_true", help="Test TokenSafetyAnalyzer class directly"
    )

    args = parser.parse_args()

    print("🔒 Token Safety Analysis - Test Suite")
    print("=" * 50)

    # Check environment
    if not check_environment():
        return

    try:
        if args.address and args.chain:
            # Test single token
            await test_single_token(args.address, args.chain)

        elif args.samples:
            # Test sample tokens
            await test_sample_tokens()

        elif args.test_analyzer:
            # Test analyzer class directly
            await test_analyzer_direct()

        else:
            print("\nUsage Options:")
            print("1. Test single token:")
            print("   python test_token_safety.py --address <ADDRESS> --chain <CHAIN>")
            print("\n2. Test sample tokens:")
            print("   python test_token_safety.py --samples")
            print("\n3. Test analyzer class:")
            print("   python test_token_safety.py --test-analyzer")

    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())