#!/usr/bin/env python3
"""
Test script for Bundler Analysis functionality
Tests the bundler detection logic and BirdEye API integration for Solana tokens

REQUIREMENTS:
- BIRDEYE_API_KEY environment variable
- All dependencies from requirements.txt

This script tests the bundler analysis integration for bundle detection.
"""

import asyncio
import sys
import os
from unittest.mock import patch, AsyncMock
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path to import data_fetchers
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from data_fetchers import (
        fetch_token_creation_info,
        fetch_token_transactions,
        detect_bundles,
        fetch_bundler_analysis,
        fetch_all_token_data,
        BundleCluster,
        CreationInfo,
        BundlerAnalysis
    )
    BUNDLER_API_AVAILABLE = True
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("Please install required dependencies: pip install -r requirements.txt")
    BUNDLER_API_AVAILABLE = False


def test_bundle_detection_algorithm():
    """Test the bundle detection algorithm with synthetic data"""
    print("🧪 Testing Bundle Detection Algorithm")
    print("-" * 40)

    # Test case 1: Clear bundle pattern
    print("Test 1: Clear bundle pattern (should detect)")
    bundle_transactions = [
        {
            "block_unix_time": 1000,
            "tx_type": "buy",
            "owner": "wallet1",
            "volume_usd": 100.0,
            "tx_hash": "hash1"
        },
        {
            "block_unix_time": 1001,
            "tx_type": "buy",
            "owner": "wallet1",
            "volume_usd": 105.0,
            "tx_hash": "hash2"
        },
        {
            "block_unix_time": 1002,
            "tx_type": "buy",
            "owner": "wallet2",
            "volume_usd": 98.0,
            "tx_hash": "hash3"
        }
    ]

    bundled, clusters, total_bundled_tokens = detect_bundles(bundle_transactions, 900)  # Created 100 seconds before
    print(f"  Bundled detected: {bundled}")
    print(f"  Cluster count: {len(clusters)}")
    print(f"  Total bundled tokens: {total_bundled_tokens}")
    if clusters:
        cluster = clusters[0]
        print(f"  Cluster size: {cluster.cluster_size}")
        print(f"  Wallet diversity: {cluster.wallet_diversity_ratio}")
        print(f"  Score: {cluster.score}")

    # Test case 2: Organic pattern (no bundles)
    print("\nTest 2: Organic pattern (should not detect)")
    organic_transactions = [
        {
            "block_unix_time": 1000,
            "tx_type": "buy",
            "owner": "wallet1",
            "volume_usd": 100.0,
            "tx_hash": "hash1"
        },
        {
            "block_unix_time": 1010,  # 10 seconds later
            "tx_type": "buy",
            "owner": "wallet2",
            "volume_usd": 200.0,
            "tx_hash": "hash2"
        },
        {
            "block_unix_time": 1020,  # 20 seconds later
            "tx_type": "buy",
            "owner": "wallet3",
            "volume_usd": 150.0,
            "tx_hash": "hash3"
        }
    ]

    bundled, clusters, total_bundled_tokens = detect_bundles(organic_transactions, 900)
    print(f"  Bundled detected: {bundled}")
    print(f"  Cluster count: {len(clusters)}")
    print(f"  Total bundled tokens: {total_bundled_tokens}")

    # Test case 3: Edge cases
    print("\nTest 3: Edge cases")

    # Empty transactions
    bundled, clusters, total_bundled_tokens = detect_bundles([], 900)
    print(f"  Empty transactions - Bundled: {bundled}, Clusters: {len(clusters)}, Tokens: {total_bundled_tokens}")

    # Single transaction
    single_tx = [bundle_transactions[0]]
    bundled, clusters, total_bundled_tokens = detect_bundles(single_tx, 900)
    print(f"  Single transaction - Bundled: {bundled}, Clusters: {len(clusters)}, Tokens: {total_bundled_tokens}")

    print("✅ Bundle detection algorithm tests completed")


async def test_creation_info_api():
    """Test the token creation info API with mocked responses"""
    print("\n🧪 Testing Token Creation Info API")
    print("-" * 40)

    # Test with successful response
    mock_response_data = {
        "data": {
            "blockUnixTime": 1697043429,
            "blockHumanTime": "2023-10-11T17:07:09Z",
            "txHash": "abc123hash"
        }
    }

    with patch('aiohttp.ClientSession.get') as mock_get:
        # Mock the context manager
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_response_data)
        mock_get.return_value.__aenter__.return_value = mock_response

        try:
            creation_info = await fetch_token_creation_info("test_token_address")

            if creation_info:
                print(f"✅ Creation info retrieved:")
                print(f"  Created at: {creation_info.created_at}")
                print(f"  Block time: {creation_info.block_unix_time}")
                print(f"  TX hash: {creation_info.creation_tx}")
            else:
                print("❌ No creation info returned")

        except Exception as e:
            print(f"❌ API test failed: {str(e)}")

    # Test with failed response
    print("\nTesting error handling:")
    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.text = AsyncMock(return_value="Not found")
        mock_get.return_value.__aenter__.return_value = mock_response

        creation_info = await fetch_token_creation_info("invalid_token")
        print(f"  Error case - Creation info: {creation_info}")


async def test_transactions_api():
    """Test the token transactions API with mocked responses"""
    print("\n🧪 Testing Token Transactions API")
    print("-" * 40)

    mock_transactions_data = {
        "data": {
            "items": [
                {
                    "block_unix_time": 1697043500,
                    "tx_type": "buy",
                    "owner": "wallet1",
                    "volume_usd": 100.0,
                    "tx_hash": "hash1"
                },
                {
                    "block_unix_time": 1697043501,
                    "tx_type": "buy",
                    "owner": "wallet2",
                    "volume_usd": 150.0,
                    "tx_hash": "hash2"
                },
                {
                    "block_unix_time": 1697043502,
                    "tx_type": "sell",  # This should be filtered out
                    "owner": "wallet3",
                    "volume_usd": 75.0,
                    "tx_hash": "hash3"
                }
            ]
        }
    }

    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_transactions_data)
        mock_get.return_value.__aenter__.return_value = mock_response

        try:
            transactions = await fetch_token_transactions("test_token_address", limit=10)

            print(f"✅ Transactions retrieved: {len(transactions)}")
            print(f"  All are buy transactions: {all(tx.get('tx_type') == 'buy' for tx in transactions)}")

            if transactions:
                print(f"  Sample transaction: {transactions[0]}")

        except Exception as e:
            print(f"❌ Transactions API test failed: {str(e)}")


async def test_bundler_analysis_integration():
    """Test the complete bundler analysis integration"""
    print("\n🧪 Testing Complete Bundler Analysis")
    print("-" * 40)

    # Mock creation info
    mock_creation_data = {
        "data": {
            "blockUnixTime": 1697043429,
            "blockHumanTime": "2023-10-11T17:07:09Z",
            "txHash": "creation_hash"
        }
    }

    # Mock transactions with bundle pattern
    mock_transactions_data = {
        "data": {
            "items": [
                {
                    "block_unix_time": 1697043500,  # 71 seconds after creation
                    "tx_type": "buy",
                    "owner": "wallet1",
                    "volume_usd": 100.0,
                    "tx_hash": "hash1"
                },
                {
                    "block_unix_time": 1697043501,  # 1 second later
                    "tx_type": "buy",
                    "owner": "wallet1",  # Same wallet
                    "volume_usd": 105.0,
                    "tx_hash": "hash2"
                },
                {
                    "block_unix_time": 1697043502,  # 1 second later
                    "tx_type": "buy",
                    "owner": "wallet2",  # Different wallet
                    "volume_usd": 95.0,
                    "tx_hash": "hash3"
                }
            ]
        }
    }

    with patch('aiohttp.ClientSession.get') as mock_get:
        # Mock responses for both API calls
        def mock_response_side_effect(*args, **kwargs):
            mock_response = AsyncMock()
            mock_response.status = 200

            # Check URL to determine which response to return
            url = args[0] if args else kwargs.get('url', '')
            if 'token_creation_info' in url:
                mock_response.json = AsyncMock(return_value=mock_creation_data)
            elif 'token/txs' in url:
                mock_response.json = AsyncMock(return_value=mock_transactions_data)

            return mock_response

        mock_get.return_value.__aenter__ = mock_response_side_effect

        try:
            analysis = await fetch_bundler_analysis("test_token_address")

            if analysis:
                print(f"✅ Bundler analysis completed:")
                print(f"  Bundles detected: {analysis.bundled_detected}")
                print(f"  Cluster count: {analysis.bundle_cluster_count}")
                print(f"  Bundled transaction percentage: {analysis.meta.get('bundled_transaction_percentage', 'N/A')}%")
                print(f"  Creation time: {analysis.creation_info.created_at if analysis.creation_info else 'None'}")

                if analysis.bundle_clusters:
                    cluster = analysis.bundle_clusters[0]
                    print(f"  First cluster: {cluster.cluster_size} txs, {cluster.unique_wallets} wallets")

                print(f"  Meta info: {analysis.meta}")
            else:
                print("❌ No analysis result returned")

        except Exception as e:
            print(f"❌ Integration test failed: {str(e)}")


async def run_all_tests():
    """Run all bundler tests"""
    if not BUNDLER_API_AVAILABLE:
        print("❌ Cannot run tests: bundler modules not available")
        return

    print("🚀 Running Bundler Analysis Tests")
    print("=" * 50)

    # Test 1: Algorithm logic
    test_bundle_detection_algorithm()

    # Test 2: API functions with mocks
    await test_creation_info_api()
    await test_transactions_api()

    # Test 3: Integration test
    await test_bundler_analysis_integration()

    print("\n" + "=" * 50)
    print("🎉 All bundler tests completed!")
    print("\nNote: These tests use mocked API responses.")
    print("For real API testing, ensure BIRDEYE_API_KEY is set and run integration tests.")


async def test_real_token(token_address: str):
    """Test bundler analysis with a real Solana token address"""
    print(f"🔍 Testing Real Token: {token_address}")
    print("=" * 50)

    # Check if API key is available
    if not os.getenv("BIRDEYE_API_KEY"):
        print("❌ BIRDEYE_API_KEY not set in environment variables")
        print("Please set it in your .env file or export it:")
        print("export BIRDEYE_API_KEY='your-api-key-here'")
        return

    try:
        print("Step 1: Testing token creation info...")
        creation_info = await fetch_token_creation_info(token_address)
        if creation_info:
            print(f"✅ Creation info retrieved:")
            print(f"  Created at: {creation_info.created_at}")
            print(f"  Block time: {creation_info.block_unix_time}")
            print(f"  TX hash: {creation_info.creation_tx}")
        else:
            print("⚠️  No creation info available")

        print("\nStep 2: Testing transaction history...")
        transactions = await fetch_token_transactions(token_address, limit=100)
        print(f"✅ Retrieved {len(transactions)} buy transactions")

        if transactions:
            print(f"  Sample transaction: {transactions[0]}")
            print(f"  Time range: {transactions[-1]['block_unix_time']} - {transactions[0]['block_unix_time']}")

        print("\nStep 3: Testing complete bundler analysis...")
        analysis = await fetch_bundler_analysis(token_address)

        if analysis:
            print(f"✅ Bundler analysis completed:")
            print(f"  Bundles detected: {analysis.bundled_detected}")
            print(f"  Cluster count: {analysis.bundle_cluster_count}")
            print(f"  Bundled transaction percentage: {analysis.meta.get('bundled_transaction_percentage', 'N/A')}%")

            if analysis.creation_info:
                print(f"  Token created: {analysis.creation_info.created_at}")

            if analysis.bundled_detected and analysis.bundle_clusters:
                print(f"  Bundle details:")
                for i, cluster in enumerate(analysis.bundle_clusters[:3]):  # Show first 3
                    print(f"    Cluster {i+1}: {cluster.cluster_size} txs, "
                          f"{cluster.unique_wallets} wallets, "
                          f"diversity: {cluster.wallet_diversity_ratio}, "
                          f"score: {cluster.score}")

            print(f"  Meta: {analysis.meta}")
        else:
            print("❌ Bundler analysis failed")

        print("\nStep 4: Testing full data pipeline integration...")
        full_data = await fetch_all_token_data(token_address, "solana")
        bundler_data = full_data.get("bundler_analysis")

        if bundler_data:
            print(f"✅ Full pipeline bundler data:")
            print(f"  Bundled detected: {bundler_data['bundled_detected']}")
            print(f"  Bundled transaction percentage: {bundler_data.get('bundled_transaction_percentage', 'N/A')}%")
            print(f"  Risk assessment: {'HIGH' if bundler_data['bundled_detected'] else 'LOW'}")
        else:
            print("❌ Bundler data missing from pipeline")

    except Exception as e:
        print(f"❌ Real token test failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if not BUNDLER_API_AVAILABLE:
        print("\n⚠️  Required dependencies not available")
        print("Install with: pip install -r ../requirements.txt")
        sys.exit(1)

    # Check command line arguments
    if len(sys.argv) == 2:
        token_address = sys.argv[1]

        # Check for help flags
        if token_address in ["-h", "--help", "help"]:
            print("Usage:")
            print("  python test_bundler_api.py                        # Run all mock tests")
            print("  python test_bundler_api.py <solana_token_address> # Test specific token")
            print("\nExamples:")
            print("  python test_bundler_api.py So11111111111111111111111111111111111111112")
            print("  python test_bundler_api.py EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
            print("  python test_bundler_api.py CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump")
            print("\nNote: Requires BIRDEYE_API_KEY environment variable for real token testing")
            sys.exit(0)

        # Test specific token
        print(f"Testing specific Solana token: {token_address}")
        asyncio.run(test_real_token(token_address))
    elif len(sys.argv) > 2:
        # Show usage for too many arguments
        print("Usage:")
        print("  python test_bundler_api.py                        # Run all mock tests")
        print("  python test_bundler_api.py <solana_token_address> # Test specific token")
        print("  python test_bundler_api.py --help                 # Show this help")
        sys.exit(1)
    else:
        # No arguments: run all mock tests
        asyncio.run(run_all_tests())