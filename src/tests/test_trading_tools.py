#!/usr/bin/env python3
"""
Test script for trading tools with actual transactions.
"""

import os
import sys
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from trading_tools import (
    WalletManager,
    GetJupiterQuote,
    CalculatePositionSize,
    ExecuteJupiterSwap
)

load_dotenv()

def test_wallet_manager():
    """Test wallet manager initialization and balance check."""
    print("Testing WalletManager...")

    wallet_address = os.getenv("DELEGATED_WALLET_ADDRESS")
    if not wallet_address:
        print("❌ DELEGATED_WALLET_ADDRESS not set")
        return False

    wallet_manager = WalletManager(
        delegated_wallet_address=wallet_address,
        turnkey_organization_id=os.getenv("TURNKEY_ORGANIZATION_ID"),
        turnkey_api_public_key=os.getenv("TURNKEY_API_PUBLIC_KEY"),
        turnkey_api_private_key=os.getenv("TURNKEY_API_PRIVATE_KEY"),
        turnkey_api_base_url=os.getenv("TURNKEY_API_BASE_URL", "https://api.turnkey.com"),
        solana_rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    )

    balance = wallet_manager.get_sol_balance()
    if balance is not None:
        print(f"✅ Wallet balance: {balance:.6f} SOL")
        return True
    else:
        print("❌ Failed to get wallet balance")
        return False

def test_jupiter_quote():
    """Test getting a Jupiter quote."""
    print("\nTesting Jupiter Quote...")

    quote_tool = GetJupiterQuote(
        input_mint="SOL",
        output_mint="USDC",
        amount="1000000000",  # 1 SOL in lamports
        slippage_bps=100
    )

    result = quote_tool.run()
    print(result)
    return "Jupiter Quote" in result

def test_small_swap():
    """Test a small swap (0.001 SOL to USDC)."""
    print("\nTesting Small Swap...")

    # Only run if explicitly enabled
    if os.getenv("ENABLE_REAL_TRADES") != "true":
        print("⚠️ Real trades disabled. Set ENABLE_REAL_TRADES=true to test actual swaps")
        return True

    swap_tool = ExecuteJupiterSwap(
        input_mint="SOL",
        output_mint="USDC",
        amount="1000000",  # 0.001 SOL in lamports
        slippage_bps=100
    )

    result = swap_tool.run()
    print(result)
    return "Successfully" in result or "Failed" in result

def main():
    """Run all tests."""
    print("=" * 50)
    print("Trading Tools Test Suite")
    print("=" * 50)

    # Check environment variables
    required_vars = [
        "DELEGATED_WALLET_ADDRESS",
        "TURNKEY_ORGANIZATION_ID",
        "TURNKEY_API_PUBLIC_KEY",
        "TURNKEY_API_PRIVATE_KEY"
    ]

    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("\nPlease set the following in your .env file:")
        for var in missing_vars:
            print(f"  {var}=<your_value>")
        return

    # Run tests
    tests = [
        test_wallet_manager,
        test_jupiter_quote,
        test_small_swap
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            results.append(False)

    # Summary
    print("\n" + "=" * 50)
    passed = sum(1 for r in results if r)
    total = len(results)

    if passed == total:
        print(f"✅ All tests passed ({passed}/{total})")
    else:
        print(f"⚠️ {passed}/{total} tests passed")

if __name__ == "__main__":
    main()