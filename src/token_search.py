#!/usr/bin/env python3
"""
Token Search Module for GoArlo Crypto Summary Bot

Handles token search functionality using BirdEye API with filtering for supported chains.
"""

import os
import aiohttp
from typing import List, Optional
from pydantic import BaseModel


class TokenSearchResult(BaseModel):
    """Model for token search result"""
    name: str
    symbol: str
    address: str
    network: str
    decimals: Optional[int] = None
    logo_uri: Optional[str] = None
    fdv: Optional[float] = None
    liquidity: Optional[float] = None
    price: Optional[float] = None
    price_change_24h_percent: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    market_cap: Optional[float] = None
    verified: bool = False
    source: Optional[str] = None


# Supported blockchain networks
SUPPORTED_CHAINS = ["solana", "ethereum", "base", "bsc", "shibarium"]


def safe_float(value) -> Optional[float]:
    """Safely convert value to float, return None if conversion fails"""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


async def search_tokens(
    keyword: str,
    search_by: str = "symbol",
    limit: int = 20
) -> List[TokenSearchResult]:
    """
    Search for tokens using BirdEye API.

    Args:
        keyword: Search term (token symbol, name, or address)
        search_by: Search criteria ("symbol", "name", or "address")
        limit: Maximum number of results to return

    Returns:
        List of TokenSearchResult objects for supported chains only
    """
    api_key = os.getenv("BIRDEYE_API_KEY")
    if not api_key:
        raise Exception("BIRDEYE_API_KEY not found in environment variables")

    print(f"🔍 Searching for tokens: '{keyword}' (by {search_by})")

    base_url = "https://public-api.birdeye.so"
    headers = {
        "X-API-KEY": api_key,
        "Accept": "application/json"
    }

    url = f"{base_url}/defi/v3/search"
    params = {
        "chain": "all",
        "keyword": keyword,
        "target": "token",
        "search_mode": "fuzzy",
        "search_by": search_by,
        "sort_by": "volume_24h_usd",
        "sort_type": "desc",
        "offset": 0,
        "limit": limit,
        "ui_amount_mode": "scaled"
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, params=params, timeout=30) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"BirdEye search API error: {response.status} - {error_text}")

                data = await response.json()

                if not data.get("success") or not data.get("data", {}).get("items"):
                    print(f"⚠️  No search results found for '{keyword}'")
                    return []

                # Extract and filter token results
                results = []
                items = data["data"]["items"]

                for item in items:
                    if item.get("type") == "token" and item.get("result"):
                        for token_data in item["result"]:
                            network = token_data.get("network", "").lower()

                            # Map network names to our supported chains
                            network_mapping = {
                                "solana": "solana",
                                "ethereum": "ethereum",
                                "base": "base",
                                "bsc": "bsc",
                                "bnb": "bsc",  # Map bnb to bsc
                                "shibarium": "shibarium"
                            }

                            mapped_network = network_mapping.get(network, network)

                            # Only include tokens from supported chains
                            if mapped_network in SUPPORTED_CHAINS:
                                try:
                                    token_result = TokenSearchResult(
                                        name=token_data.get("name", "Unknown"),
                                        symbol=token_data.get("symbol", "Unknown"),
                                        address=token_data.get("address", ""),
                                        network=mapped_network,
                                        decimals=token_data.get("decimals"),
                                        logo_uri=token_data.get("logo_uri"),
                                        fdv=safe_float(token_data.get("fdv")),
                                        liquidity=safe_float(token_data.get("liquidity")),
                                        price=safe_float(token_data.get("price")),
                                        price_change_24h_percent=safe_float(token_data.get("price_change_24h_percent")),
                                        volume_24h_usd=safe_float(token_data.get("volume_24h_usd")),
                                        market_cap=safe_float(token_data.get("market_cap")),
                                        verified=token_data.get("verified", False),
                                        source=token_data.get("source")
                                    )
                                    results.append(token_result)
                                except Exception as e:
                                    print(f"⚠️  Error parsing token result: {str(e)}")
                                    continue

                print(f"✅ Found {len(results)} verified tokens on supported chains")
                return results

        except Exception as e:
            print(f"❌ Token search failed: {str(e)}")
            raise


def display_search_results(search_result: dict) -> None:
    """Display formatted search results"""

    if not search_result["success"]:
        print(f"\n❌ {search_result['message']}")
        return

    print(f"\n✅ {search_result['message']}")
    print("=" * 80)

    for i, token in enumerate(search_result["results"], 1):
        print(f"\n{i}. {token.name} (${token.symbol})")
        print(f"   Chain: {token.network}")
        print(f"   Address: {token.address}")

        if token.price and token.price > 0:
            print(f"   Price: ${token.price:,.8f}")

        if token.market_cap and token.market_cap > 0:
            print(f"   Market Cap: ${token.market_cap:,.0f}")

        if token.volume_24h_usd and token.volume_24h_usd > 0:
            print(f"   24h Volume: ${token.volume_24h_usd:,.0f}")

        if token.price_change_24h_percent is not None:
            change_emoji = "📈" if token.price_change_24h_percent >= 0 else "📉"
            print(f"   24h Change: {change_emoji} {token.price_change_24h_percent:+.2f}%")

        if token.verified:
            print(f"   ✅ Verified")

        if token.source:
            print(f"   Source: {token.source}")

    print("\n" + "=" * 80)
    print("💡 To analyze a token, use:")
    print("   python main.py --address <ADDRESS> --chain <CHAIN>")