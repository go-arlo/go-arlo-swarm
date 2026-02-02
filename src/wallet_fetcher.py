"""
Wallet PnL fetcher for BirdEye wallet/pnl/details API
Handles fetching wallet PnL with unrealized gains/losses and progressive sell strategy
"""

import os
import aiohttp
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# Simple cache for wallet data to avoid repeated API calls
_pnl_cache = {}
_pnl_summary_cache = {}
_recent_trades_cache = {}
_cache_ttl_seconds = 30  # 30 second cache for all endpoints

# Default SOL token address
SOL_TOKEN_ADDRESS = "So11111111111111111111111111111111111111112"


class TokenPnL(BaseModel):
    """Token PnL data from wallet/pnl/details endpoint"""
    address: str
    symbol: str
    decimals: int
    last_trade_unix_time: int
    total_buy: int
    total_sell: int
    total_bought_amount: float
    total_sold_amount: float
    holding: float
    total_invested: float
    current_value: float
    unrealized_usd: float
    unrealized_percent: float
    total_usd: float
    total_percent: float
    current_price: float
    avg_buy_cost: Optional[float]
    avg_sell_cost: Optional[float]

    @classmethod
    def from_api_data(cls, data: Dict[str, Any]) -> "TokenPnL":
        """Create TokenPnL from nested API response data"""
        quantity = data.get("quantity", {})
        cashflow = data.get("cashflow_usd", {})
        pnl = data.get("pnl", {})
        pricing = data.get("pricing", {})
        counts = data.get("counts", {})

        return cls(
            address=data.get("address", ""),
            symbol=data.get("symbol", ""),
            decimals=data.get("decimals", 0),
            last_trade_unix_time=data.get("last_trade_unix_time", 0),
            total_buy=counts.get("total_buy", 0),
            total_sell=counts.get("total_sell", 0),
            total_bought_amount=quantity.get("total_bought_amount", 0),
            total_sold_amount=quantity.get("total_sold_amount", 0),
            holding=quantity.get("holding", 0),
            total_invested=cashflow.get("total_invested", 0),
            current_value=cashflow.get("current_value", 0),
            unrealized_usd=pnl.get("unrealized_usd", 0),
            unrealized_percent=pnl.get("unrealized_percent", 0),
            total_usd=pnl.get("total_usd", 0),
            total_percent=pnl.get("total_percent", 0),
            current_price=pricing.get("current_price") or 0.0,
            avg_buy_cost=pricing.get("avg_buy_cost"),
            avg_sell_cost=pricing.get("avg_sell_cost")
        )


class WalletPnLResponse(BaseModel):
    """Response from wallet PnL API"""
    success: bool
    wallet_address: str
    total_current_value: float
    total_invested: float
    total_unrealized_usd: float
    total_unrealized_percent: float
    tokens: List[TokenPnL]
    token_count: int
    fetch_timestamp: datetime
    chain: str


class WalletPnLSummary(BaseModel):
    """Response from wallet PnL summary API"""
    success: bool
    wallet_address: str
    realized_profit_percent: float
    win_rate: float
    total_realized_profit: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    fetch_timestamp: datetime
    chain: str


async def fetch_wallet_pnl(
    wallet_address: str,
    chain: str = "solana",
    sort_by: str = "last_trade",
    sort_type: str = "desc",
    limit: int = 100,
    offset: int = 0
) -> WalletPnLResponse:
    """
    Fetch wallet PnL details from BirdEye API (with 30s cache)

    Args:
        wallet_address: The wallet address to fetch PnL for
        chain: Blockchain (solana, ethereum, base, bsc, etc.)
        sort_by: Sort field (last_trade, value, etc.)
        sort_type: Sort direction (asc, desc)
        limit: Number of tokens to return (1-100)
        offset: Offset for pagination (0-10000)

    Returns:
        WalletPnLResponse with token PnL data and unrealized gains/losses
    """
    api_key = os.getenv("BIRDEYE_API_KEY")
    if not api_key:
        raise ValueError("BIRDEYE_API_KEY not set in environment variables")

    if not wallet_address:
        raise ValueError("Wallet address is required")

    # Check cache first
    cache_key = f"{chain}:{wallet_address}:{sort_by}:{limit}"
    now = datetime.now(timezone.utc)
    if cache_key in _pnl_cache:
        cached = _pnl_cache[cache_key]
        cache_age = (now - cached["timestamp"]).total_seconds()
        if cache_age < _cache_ttl_seconds:
            return cached["response"]

    chain_map = {
        "solana": "solana",
        "ethereum": "ethereum",
        "base": "base",
        "bnb": "bsc",
        "bsc": "bsc",
        "shibarium": "shibarium"
    }

    birdeye_chain = chain_map.get(chain.lower(), chain.lower())

    base_url = "https://public-api.birdeye.so"
    headers = {
        "X-API-KEY": api_key,
        "x-chain": birdeye_chain,
        "accept": "application/json"
    }

    # Build request payload for POST
    payload = {
        "wallet": wallet_address,
        "sort_by": sort_by,
        "sort_type": sort_type,
        "limit": limit,
        "offset": offset
    }

    url = f"{base_url}/wallet/v2/pnl/details"

    print(f"📊 Fetching wallet PnL for {wallet_address[:8]}... on {birdeye_chain} (fresh API call)")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                url,
                headers={**headers, "content-type": "application/json"},
                json=payload,
                timeout=30
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"BirdEye API error: {response.status} - {error_text}"
                    )

                data = await response.json()

                pnl_data = data.get("data", {})
                if not pnl_data:
                    raise Exception(f"No data in API response: {data}")
                token_list = pnl_data.get("tokens", [])
                summary = pnl_data.get("summary", {})
                cashflow = summary.get("cashflow_usd", {})
                pnl_summary = summary.get("pnl", {})

                # Parse token PnL data, excluding SOL and USDC
                tokens = []
                excluded_symbols = {"SOL", "USDC", "USDT"}

                for token_data in token_list:
                    symbol = token_data.get("symbol", "").upper()
                    if symbol in excluded_symbols:
                        continue

                    holding = token_data.get("quantity", {}).get("holding", 0)
                    if holding == 0:
                        continue

                    token_pnl = TokenPnL.from_api_data(token_data)
                    tokens.append(token_pnl)

                total_current_value = cashflow.get("current_value", 0.0)
                total_invested = cashflow.get("total_invested", 0.0)
                total_unrealized_usd = pnl_summary.get("unrealized_usd", 0.0)
                total_unrealized_percent = (
                    (total_unrealized_usd / total_invested * 100)
                    if total_invested > 0 else 0.0
                )

                print(f"✅ Fetched {len(tokens)} tokens (excluding SOL/USDC), "
                      f"current value: ${total_current_value:,.2f}, "
                      f"unrealized: {total_unrealized_percent:.2f}%")

                response = WalletPnLResponse(
                    success=True,
                    wallet_address=wallet_address,
                    total_current_value=total_current_value,
                    total_invested=total_invested,
                    total_unrealized_usd=total_unrealized_usd,
                    total_unrealized_percent=total_unrealized_percent,
                    tokens=tokens,
                    token_count=len(tokens),
                    fetch_timestamp=datetime.now(timezone.utc),
                    chain=chain
                )

                # Store in cache
                _pnl_cache[cache_key] = {
                    "timestamp": now,
                    "response": response
                }

                return response

        except Exception as e:
            print(f"❌ Error fetching wallet PnL: {str(e)}")
            raise


async def fetch_wallet_pnl_summary(
    wallet_address: Optional[str] = None,
    chain: str = "solana"
) -> WalletPnLSummary:
    """
    Fetch wallet PnL summary from BirdEye API (with 30s cache)
    Provides realized profit percentage and win rate

    Args:
        wallet_address: Wallet address (defaults to DELEGATED_WALLET_ADDRESS)
        chain: Blockchain (solana, ethereum, base, bsc, etc.)

    Returns:
        WalletPnLSummary with realized profit percentage and win rate
    """
    api_key = os.getenv("BIRDEYE_API_KEY")
    if not api_key:
        raise ValueError("BIRDEYE_API_KEY not set in environment variables")

    # Use default wallet if not provided
    wallet = wallet_address or os.getenv("DELEGATED_WALLET_ADDRESS")
    if not wallet:
        raise ValueError("No wallet address provided and DELEGATED_WALLET_ADDRESS not set")

    # Check cache first
    cache_key = f"{chain}:{wallet}"
    now = datetime.now(timezone.utc)
    if cache_key in _pnl_summary_cache:
        cached = _pnl_summary_cache[cache_key]
        cache_age = (now - cached["timestamp"]).total_seconds()
        if cache_age < _cache_ttl_seconds:
            return cached["response"]

    # Map chain names to BirdEye format
    chain_map = {
        "solana": "solana",
        "ethereum": "ethereum",
        "base": "base",
        "bnb": "bsc",
        "bsc": "bsc",
        "shibarium": "shibarium"
    }

    birdeye_chain = chain_map.get(chain.lower(), chain.lower())

    base_url = "https://public-api.birdeye.so"
    headers = {
        "X-API-KEY": api_key,
        "x-chain": birdeye_chain,
        "accept": "application/json"
    }

    url = f"{base_url}/wallet/v2/pnl/summary"
    params = {
        "wallet": wallet,
        "duration": "all"
    }

    print(f"📊 Fetching wallet PnL summary for {wallet[:8]}... on {birdeye_chain}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=30
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"BirdEye API error: {response.status} - {error_text}"
                    )

                data = await response.json()

                summary_data = data.get("data", {}).get("summary", {})
                if not summary_data:
                    raise Exception(f"No data in API response: {data}")

                pnl_stats = summary_data.get("pnl", {})
                counts_stats = summary_data.get("counts", {})

                realized_profit_percent = pnl_stats.get("realized_profit_percent", 0.0)
                win_rate = counts_stats.get("win_rate", 0.0) * 100  # Convert to percentage
                total_realized_profit = pnl_stats.get("realized_profit_usd", 0.0)
                total_trades = counts_stats.get("total_trade", 0)
                winning_trades = counts_stats.get("total_win", 0)
                losing_trades = counts_stats.get("total_loss", 0)

                print(f"✅ PnL Summary: {realized_profit_percent:.2f}% realized profit, "
                      f"{win_rate:.1f}% win rate ({winning_trades}/{total_trades} trades)")

                response = WalletPnLSummary(
                    success=True,
                    wallet_address=wallet,
                    realized_profit_percent=realized_profit_percent,
                    win_rate=win_rate,
                    total_realized_profit=total_realized_profit,
                    total_trades=total_trades,
                    winning_trades=winning_trades,
                    losing_trades=losing_trades,
                    fetch_timestamp=datetime.now(timezone.utc),
                    chain=chain
                )

                # Store in cache
                _pnl_summary_cache[cache_key] = {
                    "timestamp": now,
                    "response": response
                }

                return response

        except Exception as e:
            print(f"❌ Error fetching wallet PnL summary: {str(e)}")
            raise


class WalletPnLTracker:
    """
    Track wallet PnL over time for progressive sell decisions
    """

    def __init__(self, wallet_address: str, chain: str = "solana"):
        """
        Initialize wallet PnL tracker

        Args:
            wallet_address: Wallet address to track
            chain: Blockchain for the wallet
        """
        self.wallet_address = wallet_address
        self.chain = chain
        self.tracking_history: List[WalletPnLResponse] = []
        self.max_history = 50  # Keep last 50 snapshots

    async def update_pnl(self) -> Dict[str, Any]:
        """
        Update wallet PnL data

        Returns:
            Summary with current PnL data for all tokens
        """

        response = await fetch_wallet_pnl(
            wallet_address=self.wallet_address,
            chain=self.chain,
            sort_by="last_trade",
            limit=100
        )

        self.tracking_history.append(response)
        if len(self.tracking_history) > self.max_history:
            self.tracking_history.pop(0)

        return {
            "wallet_address": self.wallet_address,
            "total_current_value": response.total_current_value,
            "total_invested": response.total_invested,
            "total_unrealized_usd": response.total_unrealized_usd,
            "total_unrealized_percent": response.total_unrealized_percent,
            "token_count": response.token_count,
            "tokens": response.tokens,
            "timestamp": response.fetch_timestamp,
            "tracking_duration": len(self.tracking_history)
        }

    def get_pnl_history(self, limit: int = 10) -> List[WalletPnLResponse]:
        """Get recent wallet PnL tracking history"""
        return self.tracking_history[-limit:]


async def _get_cached_wallet_pnl(wallet_address: str, chain: str = "solana") -> WalletPnLResponse:
    """
    Get wallet PnL with caching to avoid repeated API calls

    Args:
        wallet_address: Wallet address to fetch PnL for
        chain: Blockchain (default: "solana")

    Returns:
        Cached or fresh WalletPnLResponse
    """
    cache_key = f"{chain}:{wallet_address}"
    now = datetime.now(timezone.utc)

    if cache_key in _pnl_cache:
        cached_data = _pnl_cache[cache_key]
        cache_age = (now - cached_data["timestamp"]).total_seconds()

        if cache_age < _cache_ttl_seconds:
            return cached_data["response"]

    response = await fetch_wallet_pnl(wallet_address, chain)

    _pnl_cache[cache_key] = {
        "timestamp": now,
        "response": response
    }

    return response


async def check_token_balance(
    token_address: str,
    chain: str = "solana",
    wallet_address: Optional[str] = None
) -> float:
    """
    Simple token balance check using cached wallet PnL API

    Args:
        token_address: Token contract address
        chain: Blockchain (default: "solana")
        wallet_address: Wallet to check (uses DELEGATED_WALLET_ADDRESS if not provided)

    Returns:
        Balance of the token (0 if not owned or error)
    """
    wallet = wallet_address or os.getenv("DELEGATED_WALLET_ADDRESS")

    if not wallet:
        print("⚠️ No wallet address configured")
        return 0.0

    try:
        pnl_response = await _get_cached_wallet_pnl(wallet, chain)

        if token_address == SOL_TOKEN_ADDRESS:
            return 0.0

        for token in pnl_response.tokens:
            if token.address.lower() == token_address.lower():
                return token.holding

        return 0.0

    except Exception as e:
        print(f"⚠️ Error checking balance for {token_address}: {e}")
        return 0.0


async def get_sol_balance_async(wallet_address: Optional[str] = None) -> Optional[float]:
    """
    Get SOL balance using Solana RPC directly

    Args:
        wallet_address: Wallet to check (uses DELEGATED_WALLET_ADDRESS if not provided)

    Returns:
        SOL balance in SOL (not lamports)
    """
    wallet = wallet_address or os.getenv("DELEGATED_WALLET_ADDRESS")

    if not wallet:
        print("⚠️ No wallet address configured")
        return None

    try:
        rpc_url = "https://api.mainnet-beta.solana.com"

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBalance",
            "params": [wallet]
        }

        headers = {
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(rpc_url, json=payload, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()

                    if "result" in data and "value" in data["result"]:
                        # Balance is returned in lamports, convert to SOL
                        lamports = data["result"]["value"]
                        sol_balance = lamports / 1e9
                        return sol_balance
                    else:
                        print(f"⚠️ Unexpected RPC response format: {data}")
                        return None
                else:
                    print(f"⚠️ Error fetching SOL balance from RPC: {response.status}")
                    return None

    except Exception as e:
        print(f"⚠️ Error getting SOL balance: {e}")
        return None


def get_sol_balance(wallet_address: Optional[str] = None) -> Optional[float]:
    """
    Get SOL balance synchronously

    Args:
        wallet_address: Wallet to check (uses DELEGATED_WALLET_ADDRESS if not provided)

    Returns:
        SOL balance or None if error
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    get_sol_balance_async(wallet_address)
                )
                return future.result()
        else:
            return asyncio.run(get_sol_balance_async(wallet_address))
    except Exception as e:
        print(f"⚠️ Error getting SOL balance: {e}")
        return None


class RecentTrade(BaseModel):
    """A recent trade (buy or sell) from the wallet"""
    transaction_hash: str
    transaction_type: str
    token_address: str
    token_symbol: str
    token_name: str
    amount: float
    usd_amount: float
    usd_price: float
    timestamp: datetime
    exchange_name: Optional[str] = None


class RecentTradesResponse(BaseModel):
    """Response containing recent buys and sells"""
    success: bool
    wallet_address: str
    recent_buys: List[RecentTrade]
    recent_sells: List[RecentTrade]
    fetch_timestamp: datetime


class TokenTradeInfo(BaseModel):
    """Simple token info for recent buys/sells"""
    address: str
    symbol: str


class RecentTradesFromPnLResponse(BaseModel):
    """Response containing PnL data with recent buys and sells arrays"""
    success: bool
    wallet_address: str
    total_current_value: float
    total_invested: float
    total_unrealized_usd: float
    total_unrealized_percent: float
    tokens: List[TokenPnL]
    token_count: int
    recent_buys: List[TokenTradeInfo]
    recent_sells: List[TokenTradeInfo]
    fetch_timestamp: datetime
    chain: str


async def fetch_recent_trades_from_pnl(
    wallet_address: str,
    chain: str = "solana",
    limit: int = 20
) -> RecentTradesFromPnLResponse:
    """
    Fetch recent trades using the PnL details endpoint from BirdEye.
    Returns PnL data along with recent_buys and recent_sells arrays.

    Args:
        wallet_address: The wallet address to fetch trades for
        chain: Blockchain (default: "solana")
        limit: Number of tokens to return (default: 20)

    Returns:
        RecentTradesFromPnLResponse with PnL data and recent buys/sells
    """
    api_key = os.getenv("BIRDEYE_API_KEY")
    if not api_key:
        raise ValueError("BIRDEYE_API_KEY not set in environment variables")

    if not wallet_address:
        raise ValueError("Wallet address is required")

    chain_map = {
        "solana": "solana",
        "ethereum": "ethereum",
        "base": "base",
        "bnb": "bsc",
        "bsc": "bsc",
        "shibarium": "shibarium"
    }

    birdeye_chain = chain_map.get(chain.lower(), chain.lower())

    base_url = "https://public-api.birdeye.so"
    headers = {
        "X-API-KEY": api_key,
        "x-chain": birdeye_chain,
        "accept": "application/json",
        "content-type": "application/json"
    }

    payload = {
        "wallet": wallet_address,
        "sort_by": "last_trade",
        "sort_type": "desc",
        "limit": limit,
        "offset": 0
    }

    url = f"{base_url}/wallet/v2/pnl/details"

    print(f"📊 Fetching recent trades for {wallet_address[:8]}... on {birdeye_chain}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=30
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"BirdEye API error: {response.status} - {error_text}"
                    )

                data = await response.json()

                pnl_data = data.get("data", {})
                if not pnl_data:
                    raise Exception(f"No data in API response: {data}")

                token_list = pnl_data.get("tokens", [])
                summary = pnl_data.get("summary", {})
                cashflow = summary.get("cashflow_usd", {})
                pnl_summary = summary.get("pnl", {})

                # Excluded tokens
                excluded_symbols = {"SOL", "USDC", "USDT"}
                excluded_addresses = {
                    "So11111111111111111111111111111111111111112",  # SOL
                    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
                }

                tokens = []
                recent_buys = []
                recent_sells = []

                for token_data in token_list:
                    symbol = token_data.get("symbol", "").upper()
                    address = token_data.get("address", "")

                    # Skip SOL, USDC, USDT
                    if symbol in excluded_symbols or address in excluded_addresses:
                        continue

                    token_pnl = TokenPnL.from_api_data(token_data)
                    tokens.append(token_pnl)

                    counts = token_data.get("counts", {})
                    total_buy = counts.get("total_buy", 0)
                    total_sell = counts.get("total_sell", 0)

                    token_info = TokenTradeInfo(
                        address=address,
                        symbol=token_data.get("symbol", "UNKNOWN")
                    )

                    # Add to recent_buys if total_buy >= 1
                    if total_buy >= 1:
                        recent_buys.append(token_info)

                    # Add to recent_sells if total_sell >= 1
                    if total_sell >= 1:
                        recent_sells.append(token_info)

                total_current_value = cashflow.get("current_value", 0.0)
                total_invested = cashflow.get("total_invested", 0.0)
                total_unrealized_usd = pnl_summary.get("unrealized_usd", 0.0)
                total_unrealized_percent = (
                    (total_unrealized_usd / total_invested * 100)
                    if total_invested > 0 else 0.0
                )

                print(f"✅ Found {len(recent_buys)} recent buys and "
                      f"{len(recent_sells)} recent sells")

                return RecentTradesFromPnLResponse(
                    success=True,
                    wallet_address=wallet_address,
                    total_current_value=total_current_value,
                    total_invested=total_invested,
                    total_unrealized_usd=total_unrealized_usd,
                    total_unrealized_percent=total_unrealized_percent,
                    tokens=tokens,
                    token_count=len(tokens),
                    recent_buys=recent_buys,
                    recent_sells=recent_sells,
                    fetch_timestamp=datetime.now(timezone.utc),
                    chain=chain
                )

        except Exception as e:
            print(f"❌ Error fetching recent trades: {str(e)}")
            raise


async def fetch_recent_trades(
    wallet_address: Optional[str] = None,
    limit: int = 10,
    transaction_type: Optional[str] = None
) -> RecentTradesResponse:
    """
    Fetch recent buy and sell trades from Moralis API (with 30s cache)

    Args:
        wallet_address: Wallet to fetch trades for (uses DELEGATED_WALLET_ADDRESS if not provided)
        limit: Number of trades to fetch per type (default: 10, max: 25)
        transaction_type: Filter by "buy", "sell", or None for both

    Returns:
        RecentTradesResponse with recent buys and sells
    """
    api_key = os.getenv("MORALIS_API_KEY")
    if not api_key:
        raise ValueError("MORALIS_API_KEY not set in environment variables")

    wallet = wallet_address or os.getenv("DELEGATED_WALLET_ADDRESS")
    if not wallet:
        raise ValueError("No wallet address provided and DELEGATED_WALLET_ADDRESS not set")

    # Check cache first (cache key includes transaction_type and limit)
    cache_key = f"{wallet}:{transaction_type}:{limit}"
    now = datetime.now(timezone.utc)
    if cache_key in _recent_trades_cache:
        cached = _recent_trades_cache[cache_key]
        cache_age = (now - cached["timestamp"]).total_seconds()
        if cache_age < _cache_ttl_seconds:
            return cached["response"]

    limit = min(limit, 25)

    base_url = f"https://solana-gateway.moralis.io/account/mainnet/{wallet}/swaps"
    headers = {
        "Accept": "application/json",
        "X-API-Key": api_key
    }

    # Build transaction types param
    if transaction_type:
        types_param = transaction_type
    else:
        types_param = "buy,sell"

    url = f"{base_url}?limit={limit}&order=DESC&transactionTypes={types_param}"

    print(f"📊 Fetching recent trades for {wallet[:8]}...")

    buys = []
    sells = []

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=30) as response:
            if response.status != 200:
                print(f"⚠️ Moralis API error: {response.status}")
                return RecentTradesResponse(
                    success=False,
                    wallet_address=wallet,
                    recent_buys=[],
                    recent_sells=[],
                    fetch_timestamp=datetime.now(timezone.utc)
                )

            data = await response.json()

            for tx in data.get("result", []):
                tx_type = tx.get("transactionType")

                # Get token info based on transaction type
                if tx_type == "buy":
                    token_data = tx.get("bought", {})
                elif tx_type == "sell":
                    token_data = tx.get("sold", {})
                else:
                    continue

                # Skip SOL/USDC/USDT
                symbol = token_data.get("symbol", "").upper()
                if symbol in {"SOL", "USDC", "USDT"}:
                    continue

                # Parse amount (handle scientific notation)
                amount_str = token_data.get("amount", "0")
                try:
                    amount = float(amount_str)
                except (ValueError, TypeError):
                    amount = 0.0

                # Parse timestamp
                ts_str = tx.get("blockTimestamp", "")
                try:
                    timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    timestamp = datetime.now(timezone.utc)

                trade = RecentTrade(
                    transaction_hash=tx.get("transactionHash", ""),
                    transaction_type=tx_type,
                    token_address=token_data.get("address", ""),
                    token_symbol=token_data.get("symbol", "UNKNOWN"),
                    token_name=token_data.get("name", "Unknown"),
                    amount=amount,
                    usd_amount=token_data.get("usdAmount", 0.0),
                    usd_price=token_data.get("usdPrice", 0.0),
                    timestamp=timestamp,
                    exchange_name=tx.get("exchangeName")
                )

                if tx_type == "buy":
                    buys.append(trade)
                else:
                    sells.append(trade)

    print(f"✅ Found {len(buys)} recent buys and {len(sells)} recent sells")

    response = RecentTradesResponse(
        success=True,
        wallet_address=wallet,
        recent_buys=buys,
        recent_sells=sells,
        fetch_timestamp=datetime.now(timezone.utc)
    )

    # Store in cache
    _recent_trades_cache[cache_key] = {
        "timestamp": now,
        "response": response
    }

    return response


if __name__ == "__main__":
    async def test():
        test_wallet = "8FbYKGy88FsdTNKKgW24ewB3BBS2VA6Z7GknELU4RfmB"

        response = await fetch_wallet_pnl(test_wallet)

        print(f"\n📊 Wallet PnL for {test_wallet[:8]}...")
        print(f"Total Current Value: ${response.total_current_value:,.2f}")
        print(f"Total Invested: ${response.total_invested:,.2f}")
        print(f"Unrealized PnL: ${response.total_unrealized_usd:,.2f} ({response.total_unrealized_percent:.2f}%)")
        print(f"Token Count: {response.token_count}")

        for token in response.tokens[:5]:
            print(f"  {token.symbol}")
            print(f"    Holding: {token.holding:.6f}")
            print(f"    Current Value: ${token.current_value:.2f}")
            print(f"    Unrealized: ${token.unrealized_usd:.4f} ({token.unrealized_percent:.2f}%)")

        print(f"\n🔍 Wallet PnL Tracking Test:")
        tracker = WalletPnLTracker(test_wallet)

        summary = await tracker.update_pnl()
        print(f"Tracking: ${summary['total_current_value']:,.2f} current value")
        print(f"Overall unrealized: {summary['total_unrealized_percent']:.2f}%")

    asyncio.run(test())
    