"""
Test Trade CLI
Execute a single buy or sell trade for testing purposes.
"""

import argparse
import asyncio
import os
import sys
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


async def test_buy(
    token_address: str,
    amount: Optional[float] = None,
    skip_analysis: bool = False,
    chain: str = "solana"
):
    """
    Test buying a single token.

    Args:
        token_address: Token contract address
        amount: SOL amount to spend (default: uses MAX_AMOUNT env or 0.1)
        skip_analysis: Skip criteria analysis and force buy
        chain: Blockchain (default: solana)
    """
    from trading_tools import AutoExecuteSwap, WalletManager
    from data_fetchers import fetch_all_token_data
    from trading_analyzer import TradingAnalyzer, TradingCriteria

    print(f"\n{'='*60}")
    print(f"TEST BUY: {token_address[:20]}...")
    print(f"{'='*60}\n")

    # Get wallet balance
    wallet_address = os.getenv("DELEGATED_WALLET_ADDRESS")
    if not wallet_address:
        print("ERROR: DELEGATED_WALLET_ADDRESS not set")
        return False

    wallet_manager = WalletManager(
        delegated_wallet_address=wallet_address,
        turnkey_organization_id=os.getenv("TURNKEY_ORGANIZATION_ID"),
        turnkey_api_public_key=os.getenv("TURNKEY_API_PUBLIC_KEY"),
        turnkey_api_private_key=os.getenv("TURNKEY_API_PRIVATE_KEY"),
        main_turnkey_api_public_key=os.getenv("MAIN_TURNKEY_API_PUBLIC_KEY"),
        main_turnkey_api_private_key=os.getenv("MAIN_TURNKEY_API_PRIVATE_KEY"),
        turnkey_api_base_url=os.getenv("TURNKEY_API_BASE_URL", "https://api.turnkey.com"),
        solana_rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    )

    sol_balance = wallet_manager.get_sol_balance()
    print(f"Wallet: {wallet_address}")
    print(f"SOL Balance: {sol_balance:.4f} SOL\n")

    if not skip_analysis:
        print("Fetching token data...")
        token_data = await fetch_all_token_data(token_address, chain)

        if not token_data:
            print("ERROR: Failed to fetch token data")
            return False

        # Display token info
        market = token_data.get("market_data", {})
        print(f"\nToken: {market.get('token_symbol', 'Unknown')}")
        print(f"Price: ${market.get('price_usd', 0):.6f}")
        print(f"FDV: ${market.get('fdv', 0):,.0f}")
        print(f"Liquidity: ${market.get('liquidity_usd', 0):,.0f}")

        # Run analysis with default criteria
        print("\nRunning trading analysis with default criteria...")
        analyzer = TradingAnalyzer(criteria=TradingCriteria(), debug=True)
        recommendation = analyzer.analyze_structured_data(token_data)

        print(f"\nDecision: {recommendation.action}")
        print(f"Confidence: {recommendation.confidence*100:.0f}%")

        if recommendation.action != "BUY":
            print(f"\nAnalysis recommends {recommendation.action}, not BUY")
            print("Failed criteria:")
            for k, v in recommendation.criteria_met.items():
                if not v:
                    print(f"  - {k}")
            print("\nUse --force to skip analysis and force buy")
            return False

    # Calculate amount
    max_amount = amount or float(os.getenv("MAX_AMOUNT", "0.1"))
    buy_amount = min(max_amount, sol_balance * 0.1)

    if sol_balance < buy_amount + 0.005:
        print(f"ERROR: Insufficient SOL balance")
        return False

    print(f"\nExecuting BUY with {buy_amount:.4f} SOL...")

    # Execute swap
    swap = AutoExecuteSwap(
        message_content=f"BUY token on {chain}",
        input_token="SOL",
        token_address=token_address
    )
    result = swap.run()

    print(f"\nResult:\n{result}")

    # Check success
    if result and "❌" not in result:
        print("\nBUY SUCCESSFUL")
        return True
    else:
        print("\nBUY FAILED")
        return False


async def test_sell(
    token_address: str,
    percent: float = 100.0,
    chain: str = "solana"
):
    """
    Test selling a token position.

    Args:
        token_address: Token contract address to sell
        percent: Percentage of holdings to sell (default: 100%)
        chain: Blockchain (default: solana)
    """
    from trading_tools import WalletManager
    import httpx

    print(f"\n{'='*60}")
    print(f"TEST SELL: {token_address[:20]}...")
    print(f"{'='*60}\n")

    wallet_address = os.getenv("DELEGATED_WALLET_ADDRESS")
    if not wallet_address:
        print("ERROR: DELEGATED_WALLET_ADDRESS not set")
        return False

    wallet_manager = WalletManager(
        delegated_wallet_address=wallet_address,
        turnkey_organization_id=os.getenv("TURNKEY_ORGANIZATION_ID"),
        turnkey_api_public_key=os.getenv("TURNKEY_API_PUBLIC_KEY"),
        turnkey_api_private_key=os.getenv("TURNKEY_API_PRIVATE_KEY"),
        main_turnkey_api_public_key=os.getenv("MAIN_TURNKEY_API_PUBLIC_KEY"),
        main_turnkey_api_private_key=os.getenv("MAIN_TURNKEY_API_PRIVATE_KEY"),
        turnkey_api_base_url=os.getenv("TURNKEY_API_BASE_URL", "https://api.turnkey.com"),
        solana_rpc_url=os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    )

    # Get token balance
    print(f"Wallet: {wallet_address}")
    print(f"Checking token balance...")

    try:
        rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTokenAccountsByOwner",
                    "params": [
                        wallet_address,
                        {"mint": token_address},
                        {"encoding": "jsonParsed"}
                    ]
                }
            )
            data = response.json()
            accounts = data.get("result", {}).get("value", [])

            if not accounts:
                print(f"ERROR: No token balance found for {token_address[:12]}...")
                return False

            token_account = accounts[0]
            parsed = token_account["account"]["data"]["parsed"]["info"]
            token_amount = int(parsed["tokenAmount"]["amount"])
            decimals = parsed["tokenAmount"]["decimals"]
            ui_amount = token_amount / (10 ** decimals)

            print(f"Token Balance: {ui_amount:.6f}")

    except Exception as e:
        print(f"ERROR: Failed to get token balance: {e}")
        return False

    # Calculate sell amount
    sell_amount = int(token_amount * (percent / 100))
    if sell_amount <= 0:
        print("ERROR: Nothing to sell")
        return False

    print(f"\nSelling {percent}% = {sell_amount / (10**decimals):.6f} tokens")

    # Execute swap (token -> SOL)
    swap_params = {
        "inputMint": token_address,
        "outputMint": "So11111111111111111111111111111111111111112",
        "amount": sell_amount,
        "slippageBps": 500
    }

    print("Executing SELL...")
    result = wallet_manager.execute_swap(swap_params)

    if result.get("success"):
        tx_hash = result.get("transactionHash", "N/A")
        out_amount = int(result.get("outputAmount", 0)) / 1e9
        print(f"\nSELL SUCCESSFUL")
        print(f"Received: {out_amount:.6f} SOL")
        print(f"TX: {tx_hash}")
        print(f"Explorer: https://solscan.io/tx/{tx_hash}")
        return True
    else:
        error = result.get("error", "Unknown error")
        print(f"\nSELL FAILED: {error}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Test single buy/sell trades",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test buy with analysis (default criteria)
  python test_trade.py buy 2nP9yKQNSGQy851iyawDvBkzkK2R2aqKArQCKc2gpump

  # Force buy without analysis
  python test_trade.py buy 2nP9yKQNSGQy851iyawDvBkzkK2R2aqKArQCKc2gpump --force

  # Buy with specific amount
  python test_trade.py buy 2nP9yKQNSGQy851iyawDvBkzkK2R2aqKArQCKc2gpump --amount 0.05

  # Sell 100% of holdings
  python test_trade.py sell 2nP9yKQNSGQy851iyawDvBkzkK2R2aqKArQCKc2gpump

  # Sell 50% of holdings
  python test_trade.py sell 2nP9yKQNSGQy851iyawDvBkzkK2R2aqKArQCKc2gpump --percent 50
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Buy command
    buy_parser = subparsers.add_parser("buy", help="Test buying a token")
    buy_parser.add_argument("address", help="Token contract address")
    buy_parser.add_argument("--amount", type=float, help="SOL amount to spend")
    buy_parser.add_argument("--force", action="store_true",
                           help="Skip analysis and force buy")
    buy_parser.add_argument("--chain", default="solana", help="Chain (default: solana)")

    # Sell command
    sell_parser = subparsers.add_parser("sell", help="Test selling a token")
    sell_parser.add_argument("address", help="Token contract address")
    sell_parser.add_argument("--percent", type=float, default=100.0,
                            help="Percentage to sell (default: 100)")
    sell_parser.add_argument("--chain", default="solana", help="Chain (default: solana)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "buy":
        success = asyncio.run(test_buy(
            token_address=args.address,
            amount=args.amount,
            skip_analysis=args.force,
            chain=args.chain
        ))
    elif args.command == "sell":
        success = asyncio.run(test_sell(
            token_address=args.address,
            percent=args.percent,
            chain=args.chain
        ))
    else:
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
