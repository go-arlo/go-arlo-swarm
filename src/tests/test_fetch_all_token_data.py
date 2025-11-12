#!/usr/bin/env python3
"""
Manual test script for fetch_all_token_data function

This script allows you to test the complete data fetching pipeline including:
- Market data from BirdEye
- Holder data from Moralis
- Bundler analysis (Solana only)
- 24h market health analysis (all chains)

Usage:
    python test_fetch_all_token_data.py <token_address> <chain>

Examples:
    python test_fetch_all_token_data.py EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v solana
    python test_fetch_all_token_data.py 0xA0b86a33E6417aB7f2a51833fBc13D3Be03D8Da0 ethereum
    python test_fetch_all_token_data.py 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 base
    python test_fetch_all_token_data.py 0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c bnb
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src directory to path to import data_fetchers
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_fetchers import fetch_all_token_data


def print_section(title: str, content: dict, indent: int = 0):
    """Pretty print a section of data"""
    prefix = "  " * indent
    print(f"\n{prefix}{'='*50}")
    print(f"{prefix}{title}")
    print(f"{prefix}{'='*50}")

    if content is None:
        print(f"{prefix}❌ No data available")
        return

    if isinstance(content, dict):
        for key, value in content.items():
            if isinstance(value, dict):
                print(f"\n{prefix}{key.upper().replace('_', ' ')}:")
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, (int, float)):
                        print(f"{prefix}  {sub_key}: {sub_value:,.2f}" if isinstance(sub_value, float) else f"{prefix}  {sub_key}: {sub_value:,}")
                    else:
                        print(f"{prefix}  {sub_key}: {sub_value}")
            elif isinstance(value, list):
                print(f"{prefix}{key}: {len(value)} items")
                if value and len(value) <= 3:  # Show first few items
                    for i, item in enumerate(value[:3]):
                        print(f"{prefix}  [{i}]: {item}")
            elif isinstance(value, (int, float)):
                print(f"{prefix}{key}: {value:,.2f}" if isinstance(value, float) else f"{prefix}{key}: {value:,}")
            else:
                print(f"{prefix}{key}: {value}")
    else:
        print(f"{prefix}{content}")


async def test_fetch_all_token_data(token_address: str, chain: str):
    """Test the complete fetch_all_token_data pipeline"""

    print(f"🚀 Testing fetch_all_token_data for:")
    print(f"   Token: {token_address}")
    print(f"   Chain: {chain}")
    print(f"   Time: {asyncio.get_event_loop().time()}")

    try:
        # Fetch all token data
        result = await fetch_all_token_data(token_address, chain)

        # Print results in organized sections
        print_section("TOKEN INFO", {
            "address": result.get("token_address"),
            "chain": result.get("chain"),
            "symbol": result.get("token_symbol"),
            "name": result.get("token_name")
        })

        print_section("MARKET DATA", result.get("market_data"))

        print_section("HOLDER DATA", result.get("holder_data"))

        # Bundler analysis (Solana only)
        bundler_data = result.get("bundler_analysis")
        if bundler_data:
            print_section("BUNDLER ANALYSIS", {
                "bundled_detected": bundler_data.get("bundled_detected"),
                "bundle_cluster_count": bundler_data.get("bundle_cluster_count"),
                "bundled_transaction_percentage": f"{bundler_data.get('bundled_transaction_percentage', 0)}%",
                "total_bundled_tokens": bundler_data.get("total_bundled_tokens")
            })

            # Risk metrics
            risk_metrics = bundler_data.get("risk_metrics")
            if risk_metrics:
                print_section("BUNDLE RISK METRICS", risk_metrics, indent=1)

            # Present impact analysis
            present_impact = bundler_data.get("present_impact_analysis")
            if present_impact:
                print_section("PRESENT IMPACT ANALYSIS", present_impact, indent=1)

            # Price action analysis
            price_action = bundler_data.get("price_action_analysis")
            if price_action:
                print_section("PRICE ACTION ANALYSIS (3-DAY)", price_action, indent=1)

            # Bundle clusters summary
            clusters = bundler_data.get("bundle_clusters", [])
            if clusters:
                print(f"\n  BUNDLE CLUSTERS: {len(clusters)} detected")
                for i, cluster in enumerate(clusters[:3]):  # Show first 3
                    print(f"    Cluster {i+1}: {cluster.get('cluster_size')} txs, {cluster.get('unique_wallets')} wallets")

        # 24h market health analysis (all chains)
        market_health = result.get("market_health_24h")
        if market_health:
            if market_health.get("market_health_available"):
                print_section("24H MARKET HEALTH", {
                    "market_health": market_health.get("market_health"),
                    "buy_pressure_pct": market_health.get("buy_pressure_pct"),
                    "sell_pressure_pct": market_health.get("sell_pressure_pct"),
                    "pressure_dominance": market_health.get("pressure_dominance"),
                    "avg_volume_per_period_usd": market_health.get("avg_volume_per_period_usd"),
                    "high_24h": market_health.get("high_24h"),
                    "low_24h": market_health.get("low_24h"),
                    "current_price": market_health.get("current_price"),
                    "price_change_24h_pct": market_health.get("price_change_24h_pct"),
                    "total_volume_24h_usd": market_health.get("total_volume_24h_usd"),
                    "volume_change_pct": market_health.get("volume_change_pct"),
                    "avg_volatility_pct": market_health.get("avg_volatility_pct"),
                    "data_points": market_health.get("data_points"),
                    "analysis_note": market_health.get("analysis_note")
                })

                # Show sentiment factors if available
                sentiment_factors = market_health.get("sentiment_factors", [])
                if sentiment_factors:
                    print(f"\n  SENTIMENT FACTORS:")
                    for factor in sentiment_factors[:5]:  # Show first 5
                        print(f"    • {factor}")
            else:
                print_section("24H MARKET HEALTH", {
                    "status": "Data not available",
                    "reason": market_health.get("analysis_note", "Unknown"),
                    "data_points": market_health.get("data_points", 0)
                })

        # Summary
        print(f"\n{'='*70}")
        print("🎯 TEST SUMMARY")
        print(f"{'='*70}")
        print(f"✅ Market data: {'OK' if result.get('market_data') else 'FAILED'}")
        print(f"✅ Holder data: {'OK' if result.get('holder_data') else 'N/A'}")
        print(f"✅ Bundler analysis: {'OK' if bundler_data and not bundler_data.get('meta', {}).get('error') else 'FAILED/N/A'}")
        print(f"✅ Market health 24h: {'OK' if market_health and market_health.get('market_health_available') else 'N/A'}")

        # Show simplified bundler summary (like user interface)
        if bundler_data and chain.lower() == "solana":
            print(f"\n🔍 USER-FACING BUNDLER SUMMARY:")
            if bundler_data.get("bundled_detected"):
                bundled_pct = bundler_data.get("bundled_transaction_percentage", 0)
                impact_risk = bundler_data.get("present_impact_analysis", {}).get("current_impact_risk", "N/A")
                print(f"  ⚠️  EARLY BUNDLES DETECTED: {bundled_pct}% (first 300 txs)")
                print(f"  Current Impact Risk: {impact_risk}")
            else:
                print(f"  ✅ NO BUNDLES DETECTED")
                print(f"  Current Impact Risk: LOW")

        return result

    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        print(f"\nFull traceback:")
        traceback.print_exc()
        return None




def main():
    """Main function to run the test"""

    # Check for required arguments
    if len(sys.argv) != 3:
        print("Usage: python test_fetch_all_token_data.py <token_address> <chain>")
        print("\nSupported chains: solana, ethereum, base, bnb, shibarium")
        print("\nExamples:")
        print("  python test_fetch_all_token_data.py EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v solana")
        print("  python test_fetch_all_token_data.py 0xA0b86a33E6417aB7f2a51833fBc13D3Be03D8Da0 ethereum")
        print("  python test_fetch_all_token_data.py 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 base")
        print("  python test_fetch_all_token_data.py 0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c bnb")
        sys.exit(1)

    token_address = sys.argv[1]
    chain = sys.argv[2].lower()

    # Validate chain
    supported_chains = ["solana", "ethereum", "base", "bnb", "shibarium"]
    if chain not in supported_chains:
        print(f"❌ Unsupported chain: {chain}")
        print(f"Supported chains: {', '.join(supported_chains)}")
        sys.exit(1)

    # Check for required environment variables
    required_env_vars = ["BIRDEYE_API_KEY"]
    optional_env_vars = ["MORALIS_API_KEY"]

    missing_required = [var for var in required_env_vars if not os.getenv(var)]
    if missing_required:
        print(f"❌ Missing required environment variables: {', '.join(missing_required)}")
        print("Please add them to your .env file")
        sys.exit(1)

    missing_optional = [var for var in optional_env_vars if not os.getenv(var)]
    if missing_optional:
        print(f"⚠️  Missing optional environment variables: {', '.join(missing_optional)}")
        print("Some features may not work properly")

    # Run the test
    try:
        result = asyncio.run(test_fetch_all_token_data(token_address, chain))

    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()