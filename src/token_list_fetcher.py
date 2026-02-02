"""
Token list fetcher for BirdEye API
Handles fetching token lists with comprehensive query parameters
"""

import os
import aiohttp
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field, validator
from enum import Enum
from dotenv import load_dotenv

load_dotenv()

class SortBy(str, Enum):
    """Sort field options for token list"""
    LIQUIDITY = "liquidity"
    MARKET_CAP = "market_cap"
    FDV = "fdv"
    VOLUME_24H = "volume_24h"
    VOLUME_1H_CHANGE_PERCENT = "volume_1h_change_percent"
    PRICE = "price"
    HOLDER = "holder"
    RECENT_LISTING_TIME = "recent_listing_time"
    LAST_TRADE_TIME = "last_trade_unix_time"


class SortType(str, Enum):
    """Sort order options"""
    DESC = "desc"
    ASC = "asc"


class UIAmountMode(str, Enum):
    """UI amount mode options"""
    SCALED = "scaled"
    RAW = "raw"


class TokenListParams(BaseModel):
    """
    Parameters for BirdEye token list API
    All parameters except sort_by and sort_type are optional
    Default values follow the 'daily driver' preset configuration
    """
    # Required parameters with defaults (daily driver preset)
    sort_by: SortBy = Field(
        default=SortBy.VOLUME_24H,
        description="Specify the sort field"
    )
    sort_type: SortType = Field(
        default=SortType.DESC,
        description="Specify the sort order"
    )

    # Liquidity filters
    min_liquidity: Optional[float] = Field(
        50000,  # Daily driver default: $50k minimum for safe execution
        description="Minimum liquidity value (inclusive)"
    )
    max_liquidity: Optional[float] = Field(
        None,
        description="Maximum liquidity value (inclusive)"
    )

    # Market cap filters
    min_market_cap: Optional[float] = Field(
        None,
        description="Minimum market cap value (inclusive)"
    )
    max_market_cap: Optional[float] = Field(
        None,
        description="Maximum market cap value (inclusive)"
    )

    # FDV filters
    min_fdv: Optional[float] = Field(
        None,
        description="Minimum FDV value (inclusive)"
    )
    max_fdv: Optional[float] = Field(
        None,
        description="Maximum FDV value (inclusive)"
    )

    # Recent listing time filters
    min_recent_listing_hours_ago: Optional[float] = Field(
        None,
        description="Minimum hours ago for recent listing (e.g., 24 for last day)"
    )
    max_recent_listing_hours_ago: Optional[float] = Field(
        None,
        description="Maximum hours ago for recent listing"
    )

    # Last trade time filters
    min_last_trade_hours_ago: Optional[float] = Field(
        None,
        description="Minimum hours ago for last trade"
    )
    max_last_trade_hours_ago: Optional[float] = Field(
        None,
        description="Maximum hours ago for last trade"
    )

    # Holder filters
    min_holder: Optional[int] = Field(
        150,
        ge=0,
        description="Minimum number of holders"
    )

    # Volume filters (1h, 2h, 4h, 8h, 24h)
    min_volume_1h_usd: Optional[float] = Field(None, ge=0)
    min_volume_2h_usd: Optional[float] = Field(None, ge=0)
    min_volume_4h_usd: Optional[float] = Field(None, ge=0)
    min_volume_8h_usd: Optional[float] = Field(None, ge=0)
    min_volume_24h_usd: Optional[float] = Field(
        None,
        ge=0
    )

    # Volume change percentage filters
    min_volume_1h_change_percent: Optional[float] = Field(None)
    min_volume_2h_change_percent: Optional[float] = Field(None)
    min_volume_4h_change_percent: Optional[float] = Field(None)
    min_volume_8h_change_percent: Optional[float] = Field(None)
    min_volume_24h_change_percent: Optional[float] = Field(None)

    # Price change percentage filters
    min_price_change_1h_percent: Optional[float] = Field(None)
    min_price_change_2h_percent: Optional[float] = Field(None)
    min_price_change_4h_percent: Optional[float] = Field(None)
    min_price_change_8h_percent: Optional[float] = Field(None)
    min_price_change_24h_percent: Optional[float] = Field(None)

    # Trade count filters
    min_trade_1h_count: Optional[int] = Field(None, ge=0)
    min_trade_2h_count: Optional[int] = Field(None, ge=0)
    min_trade_4h_count: Optional[int] = Field(None, ge=0)
    min_trade_8h_count: Optional[int] = Field(None, ge=0)
    min_trade_24h_count: Optional[int] = Field(None, ge=0)

    # Pagination
    offset: int = Field(
        default=0,
        ge=0,
        le=10000,
        description="Offset for pagination"
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=20,
        description="Number of records to return"
    )

    # UI amount mode
    ui_amount_mode: UIAmountMode = Field(
        default=UIAmountMode.SCALED,
        description="Use scaled amount for scaled UI amount tokens"
    )

    @validator('offset')
    def validate_offset_limit_sum(cls, v, values):
        """Ensure offset + limit <= 10000"""
        limit = values.get('limit', 20)
        if v + limit > 10000:
            raise ValueError(f"offset ({v}) + limit ({limit}) must be <= 10000")
        return v

    def to_api_params(self) -> Dict[str, Any]:
        """
        Convert parameters to API-ready format with datetime conversions
        """
        params = {
            "sort_by": self.sort_by.value,
            "sort_type": self.sort_type.value,
            "offset": self.offset,
            "limit": self.limit,
            "ui_amount_mode": self.ui_amount_mode.value
        }

        # Add optional numeric filters
        numeric_fields = [
            "min_liquidity", "max_liquidity",
            "min_market_cap", "max_market_cap",
            "min_fdv", "max_fdv",
            "min_holder",
            "min_volume_1h_usd", "min_volume_2h_usd", "min_volume_4h_usd",
            "min_volume_8h_usd", "min_volume_24h_usd",
            "min_volume_1h_change_percent", "min_volume_2h_change_percent",
            "min_volume_4h_change_percent", "min_volume_8h_change_percent",
            "min_volume_24h_change_percent",
            "min_price_change_1h_percent", "min_price_change_2h_percent",
            "min_price_change_4h_percent", "min_price_change_8h_percent",
            "min_price_change_24h_percent",
            "min_trade_1h_count", "min_trade_2h_count", "min_trade_4h_count",
            "min_trade_8h_count", "min_trade_24h_count"
        ]

        for field in numeric_fields:
            value = getattr(self, field, None)
            if value is not None:
                params[field] = value

        # Convert relative time to unix timestamps
        current_time = datetime.now(timezone.utc)

        # Recent listing time conversions
        if self.min_recent_listing_hours_ago is not None:
            min_time = current_time - timedelta(hours=self.min_recent_listing_hours_ago)
            params["max_recent_listing_time"] = int(min_time.timestamp())

        if self.max_recent_listing_hours_ago is not None:
            max_time = current_time - timedelta(hours=self.max_recent_listing_hours_ago)
            params["min_recent_listing_time"] = int(max_time.timestamp())

        # Last trade time conversions
        if self.min_last_trade_hours_ago is not None:
            min_time = current_time - timedelta(hours=self.min_last_trade_hours_ago)
            params["min_last_trade_unix_time"] = int(min_time.timestamp())

        if self.max_last_trade_hours_ago is not None:
            max_time = current_time - timedelta(hours=self.max_last_trade_hours_ago)
            params["max_last_trade_unix_time"] = int(max_time.timestamp())

        return params


class TokenInfo(BaseModel):
    """Token information from BirdEye API response"""
    address: str
    logo_uri: Optional[str]
    name: str
    symbol: str
    decimals: int
    market_cap: Optional[float]
    fdv: Optional[float]
    total_supply: Optional[float]
    circulating_supply: Optional[float]
    liquidity: Optional[float]
    last_trade_unix_time: Optional[int]
    volume_1h_usd: Optional[float]
    volume_24h_usd: Optional[float]
    volume_24h_change_percent: Optional[float]
    price: Optional[float]
    price_change_24h_percent: Optional[float]
    holder: Optional[int]
    recent_listing_time: Optional[int]

    class Config:
        extra = "allow"  # Allow additional fields from API


class TokenListResponse(BaseModel):
    """Response from token list API"""
    success: bool
    items: List[TokenInfo]
    has_next: bool
    total_fetched: int
    fetch_params: Dict[str, Any]
    fetch_timestamp: str
    filtered_by_ratio: Optional[bool] = False


def filter_by_volume_liquidity_ratio(
    tokens: List[TokenInfo],
    min_ratio: float = 1.5,
    max_ratio: float = 5.0
) -> List[TokenInfo]:
    """
    Filter tokens by volume/liquidity ratio

    Args:
        tokens: List of tokens to filter
        min_ratio: Minimum volume/liquidity ratio (default: 1.5)
        max_ratio: Maximum volume/liquidity ratio (default: 6.0)

    Returns:
        Filtered list of tokens within the ratio range
    """
    filtered = []
    for token in tokens:
        # Skip if missing required data
        if not token.liquidity or not token.volume_1h_usd:
            continue

        # Calculate ratio
        ratio = token.volume_1h_usd / token.liquidity

        # Filter by ratio range
        if min_ratio <= ratio <= max_ratio:
            filtered.append(token)

    return filtered


async def fetch_token_list(
    params: TokenListParams,
    chain: str = "solana",
    apply_ratio_filter: bool = False,
    min_ratio: float = 1.5,
    max_ratio: float = 6.0
) -> TokenListResponse:
    """
    Fetch token list from BirdEye API

    Args:
        params: TokenListParams object with query parameters
        chain: Blockchain to query (default: solana)
        apply_ratio_filter: Apply volume/liquidity ratio filtering
        min_ratio: Minimum volume/liquidity ratio
        max_ratio: Maximum volume/liquidity ratio

    Returns:
        TokenListResponse with token data
    """
    api_key = os.getenv("BIRDEYE_API_KEY")
    if not api_key:
        raise ValueError("BIRDEYE_API_KEY not set in environment variables")

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

    url = f"{base_url}/defi/v3/token/list"
    api_params = params.to_api_params()

    print(f"🔍 Fetching token list from BirdEye for {birdeye_chain}")
    print(f"   Parameters: {api_params}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                url,
                headers=headers,
                params=api_params,
                timeout=30
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"BirdEye API error: {response.status} - {error_text}"
                    )

                data = await response.json()

                if not data.get("success"):
                    raise Exception(f"API request failed: {data}")

                items_data = data.get("data", {}).get("items", [])
                has_next = data.get("data", {}).get("hasNext", False)

                # Parse token items
                tokens = []
                for item in items_data:
                    token = TokenInfo(
                        address=item.get("address"),
                        logo_uri=item.get("logo_uri"),
                        name=item.get("name", ""),
                        symbol=item.get("symbol", ""),
                        decimals=item.get("decimals", 0),
                        market_cap=item.get("market_cap"),
                        fdv=item.get("fdv"),
                        total_supply=item.get("total_supply"),
                        circulating_supply=item.get("circulating_supply"),
                        liquidity=item.get("liquidity"),
                        last_trade_unix_time=item.get("last_trade_unix_time"),
                        volume_1h_usd=item.get("volume_1h_usd"),
                        volume_24h_usd=item.get("volume_24h_usd"),
                        volume_24h_change_percent=item.get("volume_24h_change_percent"),
                        price=item.get("price"),
                        price_change_24h_percent=item.get("price_change_24h_percent"),
                        holder=item.get("holder"),
                        recent_listing_time=item.get("recent_listing_time")
                    )
                    tokens.append(token)

                # Apply volume/liquidity ratio filter if requested
                if apply_ratio_filter:
                    original_count = len(tokens)
                    tokens = filter_by_volume_liquidity_ratio(
                        tokens, min_ratio, max_ratio
                    )
                    print(f"✅ Fetched {original_count} tokens, "
                          f"{len(tokens)} passed ratio filter")
                else:
                    print(f"✅ Fetched {len(tokens)} tokens from BirdEye")

                return TokenListResponse(
                    success=True,
                    items=tokens,
                    has_next=has_next,
                    total_fetched=len(tokens),
                    fetch_params=api_params,
                    fetch_timestamp=datetime.now(timezone.utc).isoformat(),
                    filtered_by_ratio=apply_ratio_filter
                )

        except Exception as e:
            print(f"❌ Error fetching token list: {str(e)}")
            raise


async def fetch_all_pages(
    params: TokenListParams,
    chain: str = "solana",
    max_pages: int = 10,
    apply_ratio_filter: bool = False,
    min_ratio: float = 1.5,
    max_ratio: float = 6.0
) -> TokenListResponse:
    """
    Fetch multiple pages of tokens if needed

    Args:
        params: Initial query parameters
        chain: Blockchain to query
        max_pages: Maximum number of pages to fetch
        apply_ratio_filter: Apply volume/liquidity ratio filtering
        min_ratio: Minimum volume/liquidity ratio
        max_ratio: Maximum volume/liquidity ratio

    Returns:
        Combined TokenListResponse with all tokens
    """
    all_tokens = []
    current_params = params.copy()
    page = 0

    while page < max_pages:
        response = await fetch_token_list(
            current_params, chain, apply_ratio_filter, min_ratio, max_ratio
        )
        all_tokens.extend(response.items)

        if not response.has_next:
            break

        # Update offset for next page
        current_params.offset += current_params.limit
        page += 1

        # Rate limiting
        await asyncio.sleep(0.2)

    return TokenListResponse(
        success=True,
        items=all_tokens,
        has_next=False,
        total_fetched=len(all_tokens),
        fetch_params=params.to_api_params(),
        fetch_timestamp=datetime.now(timezone.utc).isoformat(),
        filtered_by_ratio=apply_ratio_filter
    )


class TokenListPresets:
    """Preset parameter configurations for common token filtering scenarios"""

    @staticmethod
    def high_liquidity_trending() -> TokenListParams:
        """Tokens with high liquidity and recent volume increase"""
        return TokenListParams(
            sort_by=SortBy.LIQUIDITY,
            min_liquidity=100000,  # $100k minimum
            min_volume_24h_change_percent=20,  # 20% volume increase
            min_holder=100
        )

    @staticmethod
    def new_listings() -> TokenListParams:
        """Recently listed tokens (last 24 hours)"""
        return TokenListParams(
            sort_by=SortBy.RECENT_LISTING_TIME,
            min_recent_listing_hours_ago=0,
            max_recent_listing_hours_ago=24,
            min_liquidity=10000  # $10k minimum to filter scams
        )

    @staticmethod
    def recent_listings_72h() -> TokenListParams:
        """Recently listed tokens within 72 hours (max 5 filters for API limit)"""
        return TokenListParams(
            sort_by=SortBy.RECENT_LISTING_TIME,
            max_recent_listing_hours_ago=72,
            min_liquidity=50000,
            min_holder=100,
            min_volume_24h_usd=None,
            min_volume_1h_change_percent=None,
            min_price_change_1h_percent=None,
            min_trade_1h_count=None
        )

    @staticmethod
    def high_volume_movers() -> TokenListParams:
        """High volume tokens with significant price movement"""
        return TokenListParams(
            sort_by=SortBy.VOLUME_24H,
            min_volume_24h_usd=1000000,
            min_price_change_24h_percent=10
        )

    @staticmethod
    def established_tokens() -> TokenListParams:
        """Well-established tokens with good metrics"""
        return TokenListParams(
            sort_by=SortBy.MARKET_CAP,
            min_market_cap=1000000,
            min_holder=1000,
            min_liquidity=50000
        )

    @staticmethod
    def momentum_plays() -> TokenListParams:
        """High momentum tokens with strong volume and liquidity"""
        return TokenListParams(
            sort_by=SortBy.VOLUME_1H_CHANGE_PERCENT,
            sort_type=SortType.DESC,
            min_fdv=500000,
            min_liquidity=100000,
            min_volume_24h_usd=1000000
        )

    @staticmethod
    def daily_driver() -> TokenListParams:
        """Daily driver settings for consistent trading opportunities (max 5 filters)"""
        return TokenListParams(
            sort_by=SortBy.LIQUIDITY,
            sort_type=SortType.DESC,
            min_liquidity=50000,
            min_holder=150,
            min_volume_24h_usd=200000,
            limit=20,
            min_volume_1h_change_percent=None,
            min_price_change_1h_percent=None,
            min_trade_1h_count=None
        )

    @staticmethod
    def high_momentum() -> TokenListParams:
        """High momentum settings for aggressive plays"""
        return TokenListParams(
            sort_by=SortBy.VOLUME_1H_CHANGE_PERCENT,
            sort_type=SortType.DESC,
            min_liquidity=100000,
            min_volume_24h_usd=500000,
            min_volume_1h_change_percent=25,
            min_price_change_1h_percent=-3,
            min_trade_1h_count=50,
            limit=20
        )

    @staticmethod
    def volume_liquidity_balanced() -> TokenListParams:
        """
        Volume/Liquidity balanced preset for optimal trading opportunities

        Token Age: 30 min - 72 hours
        Min Liquidity: $50,000
        Min 1h Volume: $100,000
        Volume/Liquidity ratio: 1.5x - 6x (filtered in post-processing)
        """
        return TokenListParams(
            sort_by=SortBy.VOLUME_1H_CHANGE_PERCENT,  # Sort by momentum
            sort_type=SortType.DESC,
            min_recent_listing_hours_ago=0.5,
            max_recent_listing_hours_ago=72,
            min_liquidity=50000,
            min_volume_1h_usd=100000,
            min_holder=100,
            min_volume_24h_usd=None,
            min_volume_1h_change_percent=None,
            min_price_change_1h_percent=None,
            min_trade_1h_count=None,
            limit=20
        )

    @staticmethod
    def optimized_default() -> TokenListParams:
        """
        New optimized default filter for consistent trading opportunities

        Token Age: 30 min - 72 hours
        Min Liquidity: $50,000
        Min 1h Volume: $75,000
        Volume/Liquidity ratio: 1.5x - 5x (filtered in post-processing)
        Min Holder Count: 100

        Note: Removed 24h volume filter to stay within BirdEye's 5-filter limit
        """
        return TokenListParams(
            sort_by=SortBy.LIQUIDITY,
            sort_type=SortType.DESC,
            min_recent_listing_hours_ago=0.5,
            max_recent_listing_hours_ago=72,
            min_liquidity=50000,
            min_volume_1h_usd=75000,
            min_holder=100,
            min_volume_24h_usd=None,
            min_volume_1h_change_percent=None,
            min_price_change_1h_percent=None,
            min_trade_1h_count=None,
            limit=20
        )


if __name__ == "__main__":
    # Test the fetcher with different presets
    async def test_fetch():
        # Test with high liquidity trending preset
        params = TokenListPresets.high_liquidity_trending()
        response = await fetch_token_list(params)

        print(f"\n📊 High Liquidity Trending Tokens:")
        for token in response.items[:5]:  # Show first 5
            print(f"  - {token.symbol}: ${token.price:.6f} "
                  f"(Liq: ${token.liquidity:,.0f}, "
                  f"Vol24h: ${token.volume_24h_usd:,.0f})")

    asyncio.run(test_fetch())
