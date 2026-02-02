#!/usr/bin/env python3
"""
GoArlo Token Analysis

A streamlined implementation that:
1. Fetches market and holder data from external APIs
2. Initializes agency with pre-fetched data
3. Processes sentiment analysis and narrative generation
4. Returns structured token summary
"""

import asyncio
import argparse
import os
import sys
import re
from typing import Dict, Any, Optional, Set
from datetime import datetime
from cachetools import TTLCache
from asyncio import Event, Semaphore
from dotenv import load_dotenv

# Load environment variables FIRST (before imports that need them)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# FastAPI imports
from fastapi import FastAPI, HTTPException, Depends, Body, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import after path modification (env vars are now loaded)
try:
    from data_fetchers import fetch_all_token_data
    from token_search import search_tokens
    # Import telegram_handler instance (circular import resolved via lazy imports in telegram_handler.py)
    import telegram_handler as telegram_handler_module
    telegram_handler = telegram_handler_module.telegram_handler
    # Import token list router
    from token_list_router import router as token_list_router
    from token_list_scheduler import get_scheduler
    # Import wallet router
    from wallet_router import router as wallet_router
    # Import trading router
    from trading_router import router as trading_router
except ImportError as e:
    # Handle case where modules aren't found
    print(f"Warning: Import error - {e}")
    telegram_handler = None
    token_list_router = None
    wallet_router = None
    trading_router = None

# Momentum trading imports
from token_list_fetcher import fetch_token_list, TokenListPresets
from wallet_fetcher import fetch_wallet_pnl
from trading_analyzer import TradingAnalyzer, get_conservative_criteria, get_moderate_criteria, get_aggressive_criteria

# In-memory cache and deduplication setup
# Cache analysis results for 5 minutes (300 seconds)
analysis_cache = TTLCache(maxsize=1000, ttl=300)

# Track ongoing analyses to prevent duplicate processing
# Format: {cache_key: {'event': Event(), 'result': None, 'timestamp': datetime}}
ongoing_analyses: Dict[str, Dict[str, Any]] = {}

# Concurrency limiter - prevent server overload by limiting concurrent analyses
analysis_semaphore = Semaphore(10)

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events"""
    # Startup
    if token_list_router is not None:
        scheduler = get_scheduler()
        scheduler.start()
        print("✅ Token List Scheduler started")

    yield

    # Shutdown
    if token_list_router is not None:
        scheduler = get_scheduler()
        scheduler.stop()
        print("✅ Token List Scheduler stopped")


# FastAPI app setup
app = FastAPI(
    title="GoArlo Crypto Analysis API",
    description="API for token analysis and extraction",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin for origin in [
            "https://goarlo.ai",
            "https://www.goarlo.ai",
            os.getenv("PUBLIC_URL")
        ] if origin is not None
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount token list router if available
if token_list_router is not None:
    app.include_router(token_list_router)
    print("✅ Token List API routes mounted at /token-list/*")

# Mount wallet router if available
if wallet_router is not None:
    app.include_router(wallet_router)
    print("✅ Wallet API routes mounted at /wallet/*")
# Mount trading router if available
if trading_router is not None:
    app.include_router(trading_router)
    print("✅ Trading API routes mounted at /trading/*")

# Custom exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log detailed validation error messages for debugging"""
    error_details = []
    for error in exc.errors():
        error_details.append({
            "field": ".".join(str(x) for x in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    print(f"❌ Validation Error: {error_details}")
    

    raise exc

# Pydantic models
class TextAnalysisRequest(BaseModel):
    text: str
    link: str

class TokenExtractionResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

class TokenAnalysisResponse(BaseModel):
    success: bool
    message: str
    token_data: Optional[Dict[str, Any]] = None
    analysis_data: Optional[Dict[str, Any]] = None
    twitter_data: Optional[Dict[str, Any]] = None

# API Key verification
from auth import verify_api_key, verify_api_key_optional, get_public_url


def format_price(price: float) -> str:
    """
    Format price to avoid scientific notation and show appropriate decimal places.
    
    Args:
        price: Price value to format
        
    Returns:
        Formatted price string without scientific notation
    """
    if price == 0:
        return "0"
    
    # For very small prices (< 0.01), show more decimal places
    if price < 0.01:
        # Format with enough precision to show meaningful digits
        formatted = f"{price:.12f}"
        # Remove trailing zeros
        formatted = formatted.rstrip('0').rstrip('.')
        return formatted
    # For prices between 0.01 and 1, show 6 decimal places
    elif price < 1:
        formatted = f"{price:.6f}"
        formatted = formatted.rstrip('0').rstrip('.')
        return formatted
    # For prices >= 1, show 2 decimal places
    else:
        return f"{price:.2f}"


def holder_icon(concentration):
    """Return concentration icon based on top 10 concentration percentage"""
    if concentration > 35:
        return "🐋 HEAVY"
    elif concentration > 20:
        return "🦈 MODERATE"
    elif concentration > 10:
        return "🐟 BALANCED"
    else:
        return "🐚 DECENTRALIZED"


def _format_safety_analysis(safety_data: Optional[Dict], chain: str) -> str:
    """Format safety analysis data for agency consumption"""

    if not safety_data:
        return f"- Safety Analysis: ❌ UNAVAILABLE for {chain} chain"

    try:
        overall_risk = safety_data.get('overall_risk', 'UNKNOWN')
        contract_control = safety_data.get('contract_control', {})
        holder_control = safety_data.get('holder_control', {})

        result = f"- Overall Risk Level: {overall_risk}\n"
        result += f"- Contract Control: {contract_control.get('status', 'unknown').upper()} - {contract_control.get('reason', 'No data')}\n"
        result += f"- Holder Control: {holder_control.get('status', 'unknown').upper()} - {holder_control.get('reason', 'No data')}"

        # Add chain-specific data
        if chain.lower() == "solana":
            key_metrics = safety_data.get('key_metrics', {})
            if key_metrics.get('jupiter_strict_list'):
                result += "\n- Jupiter Strict List: ✅ VERIFIED"
            if key_metrics.get('mutable_metadata'):
                result += "\n- Metadata: 🔄 MUTABLE"

        else:  # EVM chains
            security_checks = safety_data.get('security_checks', {})
            liquidity_analysis = safety_data.get('liquidity_analysis', {})
            key_metrics = safety_data.get('key_metrics', {})

            result += f"\n- Security Checks: {security_checks.get('status', 'unknown').upper()} - {security_checks.get('reason', 'No data')}"
            result += f"\n- Liquidity Analysis: {liquidity_analysis.get('status', 'unknown').upper()} - {liquidity_analysis.get('reason', 'No data')}"

            if key_metrics.get('is_open_source'):
                result += "\n- Contract: ✅ OPEN SOURCE"
            if key_metrics.get('buy_tax', 0) > 0 or key_metrics.get('sell_tax', 0) > 0:
                result += f"\n- Taxes: Buy {key_metrics.get('buy_tax', 0)}% / Sell {key_metrics.get('sell_tax', 0)}%"

        return result

    except Exception as e:
        return f"- Safety Analysis: ❌ ERROR - {str(e)}"


def _format_market_health(health_data: Dict[str, Any]) -> str:
    """Format 24h market health data for the message"""
    if not health_data:
        return "- Market health data unavailable"

    if not health_data.get('market_health_available'):
        return f"- Market health analysis unavailable: {health_data.get('analysis_note', 'No data')}"

    vol_change = health_data.get('volume_change_pct')
    vol_change_str = f"{vol_change:+.1f}%" if vol_change is not None else "N/A"
    
    result = f"""- market_health: {health_data.get('market_health', 'N/A')}
        - buy_pressure_pct: {health_data.get('buy_pressure_pct', 'N/A')}
        - sell_pressure_pct: {health_data.get('sell_pressure_pct', 'N/A')}
        - pressure_dominance: {health_data.get('pressure_dominance', 'N/A')}
        - avg_trade_size_usd: {health_data.get('avg_trade_size_usd', 'N/A')}
        - volume_change_pct: {vol_change_str}
        - avg_volatility_pct: {health_data.get('avg_volatility_pct', 'N/A')}"""

    return result


def format_token_report(data: Dict[str, Any]) -> str:
    """
    Format comprehensive token analysis report.

    Args:
        data: Full analysis data dict containing token_info, market_data,
              holder_data, safety_analysis, bundler_analysis, etc.

    Returns:
        Formatted report text with complete analysis and metrics
    """
    token_info = data.get("token_info", {})
    market_data = data.get("market_data", {})

    # Create token header
    symbol = token_info.get('symbol', 'UNKNOWN')
    chain = token_info.get('chain', 'unknown').title()
    address = token_info.get('address', '')
    formatted_output = f"💠 **Token:** ${symbol} 🌐 **Chain:** {chain}\n"
    formatted_output += f"🔗 {address}\n"

    # Add market data section
    if market_data:
        formatted_output += "\n📊 Market Data:\n"
        price = market_data.get('price_usd', 0)
        formatted_output += f"  💰 Price: ${format_price(price)}\n"

        fdv = market_data.get('fdv_usd', 0)
        formatted_output += f"  🧮 FDV: ${fdv:,.0f}\n"

        liquidity = market_data.get('liquidity_usd', 0)
        formatted_output += f"  💧 Liquidity: ${liquidity:,.0f}\n"

        volume = market_data.get('volume_24h_usd', 0)
        formatted_output += f"  🔁 24h Volume: ${volume:,.0f}\n"

        total_supply = market_data.get('total_supply')
        if total_supply is not None:
            formatted_output += f"  🪙 Total Supply: {total_supply:,}\n"

        circulating_supply = market_data.get('circulating_supply')
        if circulating_supply is not None:
            formatted_output += f"  💫 Circulating Supply: {circulating_supply:,}\n"

    # Add token safety section
    if data.get('safety_analysis'):
        safety = data['safety_analysis']
        formatted_output += "\n🔐 Token Safety:\n"
        
        # Overall risk icon
        overall_risk = safety.get('overall_risk', 'UNKNOWN')
        risk_icon = {
            'HIGH': '🔴',
            'MEDIUM': '🟠',
            'LOW': '🟢',
            'UNKNOWN': '⚪'
        }.get(overall_risk, '⚪')
        
        formatted_output += f"  {risk_icon} Overall Risk: {overall_risk}\n"
        
        # Chain-specific information
        chain_lower = token_info.get('chain', '').lower()
        key_metrics = safety.get('key_metrics', {})
        contract = safety.get('contract_control', {})
        holder_ctrl = safety.get('holder_control', {})
        
        if chain_lower == 'solana':
            # Solana: Show contract control separately
            if contract:
                status_icon = '✅' if contract.get('status') == 'positive' else '⚠️' if contract.get('status') == 'neutral' else '❌'
                formatted_output += f"  {status_icon} Contract: {contract.get('reason', 'No data')}\n"
            
            # Solana: Show holder control
            if holder_ctrl:
                status_icon = '✅' if holder_ctrl.get('status') == 'positive' else '⚠️' if holder_ctrl.get('status') == 'neutral' else '❌'
                formatted_output += f"  {status_icon} Holder Control: {holder_ctrl.get('reason', 'No data')}\n"
            
            # Solana-specific metrics
            if key_metrics.get('jupiter_strict_list'):
                formatted_output += f"  ✅ Jupiter Strict List: Verified\n"
            
            if key_metrics.get('mutable_metadata'):
                formatted_output += f"  ⚠️ Metadata: Mutable\n"
            else:
                formatted_output += f"  ✅ Metadata: Immutable\n"
        else:
            # EVM: Show contract control and security checks
            security = safety.get('security_checks', {})
            
            # Check status
            contract_positive = contract.get('status') == 'positive'
            security_positive = security.get('status') == 'positive'
            is_open_source = key_metrics.get('is_open_source', False)
            
            # Always show Contract line (renouncement status)
            if contract:
                status_icon = '✅' if contract_positive else '⚠️' if contract.get('status') == 'neutral' else '❌'
                formatted_output += f"  {status_icon} Contract: {contract.get('reason', 'No data')}\n"
            
            # Show Security line
            if security_positive and is_open_source:
                # All security checks passed - show combined positive message
                verified_items = []
                if is_open_source:
                    verified_items.append("Open source")
                if not key_metrics.get('is_honeypot', False):
                    verified_items.append("No honeypot")
                if not key_metrics.get('is_blacklisted', False):
                    verified_items.append("Not blacklisted")
                
                formatted_output += f"  ✅ Security: Verified ({', '.join(verified_items)})\n"
            else:
                # Show security issues
                if security and security.get('status') != 'positive':
                    status_icon = '⚠️' if security.get('status') == 'neutral' else '❌'
                    formatted_output += f"  {status_icon} Security: {security.get('reason', 'No data')}\n"
                elif not is_open_source:
                    formatted_output += f"  ⚠️ Security: Closed source contract\n"
            
            # EVM: Show holder control
            if holder_ctrl:
                status_icon = '✅' if holder_ctrl.get('status') == 'positive' else '⚠️' if holder_ctrl.get('status') == 'neutral' else '❌'
                formatted_output += f"  {status_icon} Holder Control: {holder_ctrl.get('reason', 'No data')}\n"
            
            # Show taxes if present
            buy_tax = key_metrics.get('buy_tax', 0)
            sell_tax = key_metrics.get('sell_tax', 0)
            if buy_tax > 0 or sell_tax > 0:
                formatted_output += f"  ⚠️ Taxes: Buy {buy_tax}% / Sell {sell_tax}%\n"

    # Add holder data section with concentration icons
    if data.get('holder_data'):
        holder_data = data['holder_data']
        formatted_output += "\n👥 Holder Data:\n"

        holders = holder_data.get('total_holders', 0)
        formatted_output += f"  Total Holders: {holders:,}\n"

        concentration = holder_data.get('top10_concentration', 0)
        if concentration > 0:
            icon = holder_icon(concentration)
            formatted_output += f"  Top 10 Concentration: {concentration:.1f}% {icon}\n"

    # Add bundler analysis section for Solana
    if data.get('bundler_analysis') and token_info.get('chain', '').lower() == 'solana':
        bundler = data['bundler_analysis']
        formatted_output += "\n🔍 Bundler Analysis:\n"

        if bundler.get('bundled_detected'):
            # Show bundled percentage
            bundled_pct = bundler.get('bundled_transaction_percentage', 0)
            if bundled_pct > 0:
                formatted_output += f"  ⚠️  EARLY BUNDLES DETECTED: {bundled_pct:.1f}% (first 300 txs)\n"

            # Show current impact risk with bomb icon
            current_risk = bundler.get('present_impact_analysis', {}).get('current_impact_risk', 'UNKNOWN')
            formatted_output += f"  🧨 Current Impact Risk: {current_risk}\n"
        else:
            formatted_output += "  ✅ NO BUNDLES DETECTED\n"
            formatted_output += "  🧨 Current Impact Risk: LOW\n"

    # Add 24h market health section
    if data.get('market_health_24h'):
        health = data['market_health_24h']
        if health.get('market_health_available'):
            formatted_output += "\n📈 24h Market Health:\n"
            formatted_output += f"  Overall Health: {health.get('market_health', 'N/A')}\n"

            buy_pct = health.get('buy_pressure_pct', 'N/A')
            sell_pct = health.get('sell_pressure_pct', 'N/A')
            pressure_dominance = health.get('pressure_dominance', 'N/A')
            if buy_pct != 'N/A' and sell_pct != 'N/A':
                formatted_output += f"  Buy/Sell Pressure: {buy_pct:.1f}% / {sell_pct:.1f}% ({pressure_dominance})\n"
            else:
                formatted_output += f"  Buy/Sell Pressure: {buy_pct} / {sell_pct} ({pressure_dominance})\n"

            vol_change = health.get('volume_change_pct')
            if vol_change is not None:
                formatted_output += f"  Volume Change: {vol_change:+.1f}%\n"
            else:
                formatted_output += f"  Volume Change: N/A\n"

            volatility = health.get('avg_volatility_pct', 'N/A')
            if volatility != 'N/A':
                formatted_output += f"  Volatility: {volatility:.1f}%\n"
            else:
                formatted_output += f"  Volatility: {volatility}\n"

    # Add sentiment rating with TweetScout score first, then Grok analysis
    sentiment_data = data.get("sentiment_data")
    if sentiment_data:
        formatted_output += "\n💭 Sentiment Analysis:\n"

        # TweetScout score (first, if available)
        score = sentiment_data.get("tweet_scout_score")
        if score is not None:
            if score >= 1000:
                rating_icon = '🟢'
            elif score >= 500:
                rating_icon = '🟡'
            elif score >= 200:
                rating_icon = '🟠'
            else:
                rating_icon = '🔴'
            formatted_output += f"  {rating_icon} TweetScout Score: {score:.2f}\n"

        # Grok sentiment analysis
        grok_sentiment = sentiment_data.get("grok_sentiment")
        grok_scam = sentiment_data.get("grok_scam_assessment")
        grok_overview = sentiment_data.get("grok_overview")

        if grok_sentiment:
            sentiment_icon = {
                'Positive': '🟢',
                'Neutral': '🟡',
                'Negative': '🔴'
            }.get(grok_sentiment, '⚪')
            formatted_output += f"  {sentiment_icon} Grok Sentiment: {grok_sentiment}\n"

        if grok_scam:
            scam_icon = {
                'Unlikely': '✅',
                'Uncertain': '🔶',
                'Likely': '🚨'
            }.get(grok_scam, '⚪')
            formatted_output += f"  {scam_icon} Scam Risk: {grok_scam}\n"

        if grok_overview:
            formatted_output += f"  📝 {grok_overview}\n"

    return formatted_output


# Alias for backwards compatibility with telegram_handler
format_analysis_for_twitter = format_token_report


def preview_tweet_format(data: Dict[str, Any]) -> str:
    """
    Preview how the analysis will look when formatted for Twitter.

    Args:
        data: Full analysis data dict

    Returns:
        Formatted tweet text for preview
    """
    formatted_tweet = format_token_report(data)

    print(f"\n📱 TWITTER PREVIEW ({len(formatted_tweet)} characters):")
    print("─" * 50)
    print(formatted_tweet)
    print("─" * 50)
    print(f"✅ Full analysis formatted for Twitter posting")

    return formatted_tweet


def extract_tweet_id(twitter_url: str) -> Optional[str]:
    """
    Extract tweet ID from Twitter URL

    Args:
        twitter_url: Twitter URL (e.g., https://twitter.com/user/status/1234567890)

    Returns:
        Tweet ID string or None if not found
    """
    import re

    # Pattern to match Twitter URLs and extract tweet ID
    # Must be at start of string or after protocol
    pattern = r'^(?:https?://)?(?:www\.)?(twitter\.com|x\.com)/[^/]+/status/(\d+)'
    match = re.search(pattern, twitter_url)

    if match:
        return match.group(2)  # Group 2 is the tweet ID, group 1 is the domain
    return None


async def post_twitter_reply(
    data: Dict[str, Any],
    reply_to_tweet: str
) -> Dict[str, Any]:
    """
    Post analysis as a Twitter reply using tweepy

    Args:
        data: Full analysis data dict
        reply_to_tweet: Tweet ID to reply to

    Returns:
        Dict with success status and details
    """
    try:
        # Format the analysis for Twitter
        formatted_tweet = format_token_report(data)

        # Check for required Twitter credentials
        required_vars = [
            "TWITTER_API_KEY",
            "TWITTER_API_KEY_SECRET",
            "TWITTER_ACCESS_TOKEN",
            "TWITTER_ACCESS_TOKEN_SECRET"
        ]

        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            error_msg = f"Missing Twitter API credentials: {', '.join(missing_vars)}"
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "tweet_content": None,
                "error": error_msg
            }

        # Import tweepy
        try:
            import tweepy
        except ImportError:
            error_msg = "tweepy not installed. Install with: pip install tweepy"
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "tweet_content": None,
                "error": error_msg
            }

        # Create Twitter client
        client = tweepy.Client(
            consumer_key=os.getenv("TWITTER_API_KEY"),
            consumer_secret=os.getenv("TWITTER_API_KEY_SECRET"),
            access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
            access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
        )

        # Post the tweet reply
        print(f"🐦 Posting Twitter reply to tweet {reply_to_tweet}")
        print(f"📝 Tweet content ({len(formatted_tweet)} chars):")
        print(f"   {formatted_tweet[:100]}{'...' if len(formatted_tweet) > 100 else ''}")

        response = client.create_tweet(
            text=formatted_tweet,
            in_reply_to_tweet_id=reply_to_tweet
        )

        if response and response.data:
            tweet_id = response.data['id']
            print(f"✅ Successfully posted reply: https://twitter.com/user/status/{tweet_id}")
            return {
                "success": True,
                "tweet_content": formatted_tweet,
                "tweet_id": tweet_id,
                "tweet_url": f"https://twitter.com/user/status/{tweet_id}",
                "error": None
            }
        else:
            error_msg = "Failed to post tweet: No response data"
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "tweet_content": formatted_tweet,
                "error": error_msg
            }

    except tweepy.TooManyRequests:
        error_msg = "Twitter API rate limit exceeded. Please try again later."
        print(f"❌ {error_msg}")
        return {
            "success": False,
            "tweet_content": formatted_tweet if 'formatted_tweet' in locals() else None,
            "error": error_msg
        }
    except tweepy.Forbidden:
        error_msg = "Twitter API access forbidden. Check your API permissions."
        print(f"❌ {error_msg}")
        return {
            "success": False,
            "tweet_content": formatted_tweet if 'formatted_tweet' in locals() else None,
            "error": error_msg
        }
    except tweepy.Unauthorized:
        error_msg = "Twitter API unauthorized. Check your API credentials."
        print(f"❌ {error_msg}")
        return {
            "success": False,
            "tweet_content": formatted_tweet if 'formatted_tweet' in locals() else None,
            "error": error_msg
        }
    except Exception as e:
        error_msg = f"Error posting tweet reply: {str(e)}"
        print(f"❌ {error_msg}")
        return {
            "success": False,
            "tweet_content": formatted_tweet if 'formatted_tweet' in locals() else None,
            "error": error_msg
        }


async def analyze_token_with_cache(
    token_address: str,
    chain: str = None,
    token_symbol: str = None,
    analyze_for_trading: bool = False,
    auto_execute: bool = False,
    input_token: str = "SOL",
    portfolio_percent: float = None
) -> Dict[str, Any]:
    """
    Cached and deduplicated wrapper around analyze_token with concurrency limiting.
    
    - Checks cache first (5 min TTL)
    - Deduplicates concurrent requests for the same token
    - Limits concurrent analyses to prevent server overload
    - Performs fresh analysis if needed
    
    Args:
        token_address: Contract address of the token
        chain: Blockchain name (required)
        token_symbol: Token symbol (extracted from market data if not provided)
        
    Returns:
        Dict containing the complete analysis results
    """
    # Chain is required
    if not chain:
        raise ValueError("Chain parameter is required")
    
    cache_key = f"{chain.lower()}:{token_address.lower()}"
    
    # Step 1: Check cache
    if cache_key in analysis_cache:
        cached_result = analysis_cache[cache_key]
        cache_age = (datetime.now() - cached_result['timestamp']).seconds
        print(f"💾 Using cached analysis for {token_address} (age: {cache_age}s)")
        return cached_result['result']
    
    # Step 2: Check if analysis is already in progress (deduplication)
    if cache_key in ongoing_analyses:
        print(f"⏳ Analysis already in progress for {token_address}, waiting for result...")
        analysis_info = ongoing_analyses[cache_key]
        
        # Wait for the ongoing analysis to complete
        await analysis_info['event'].wait()
        
        # Return the result from the first request
        print(f"✅ Received result from ongoing analysis for {token_address}")
        return analysis_info['result']
    
    # Step 3: Start new analysis with concurrency limiting
    print(f"🚀 Starting fresh analysis for {token_address}")
    ongoing_analyses[cache_key] = {
        'event': Event(),
        'result': None,
        'timestamp': datetime.now()
    }
    
    try:
        # Use semaphore to limit concurrent analyses
        async with analysis_semaphore:
            print(f"🔒 Acquired analysis slot for {token_address}")
            
            # Perform the actual analysis
            result = await analyze_token(
                token_address,
                chain,
                token_symbol,
                analyze_for_trading=analyze_for_trading,
                auto_execute=auto_execute,
                input_token=input_token,
                portfolio_percent=portfolio_percent
            )
            
            # Store result for waiting requests
            ongoing_analyses[cache_key]['result'] = result
            
            # Cache successful results
            if result.get('success'):
                analysis_cache[cache_key] = {
                    'result': result,
                    'timestamp': datetime.now()
                }
                print(f"💾 Stored fresh analysis result in cache for {token_address}")
            
            # Wake up all waiting requests
            ongoing_analyses[cache_key]['event'].set()
            
            return result
        
    except Exception as e:
        # On error, still wake up waiting requests with error result
        error_result = {
            "success": False,
            "error": f"Analysis failed: {str(e)}",
            "data": None
        }
        ongoing_analyses[cache_key]['result'] = error_result
        ongoing_analyses[cache_key]['event'].set()
        return error_result
        
    finally:
        # Clean up ongoing analysis tracking after a short delay
        async def cleanup():
            await asyncio.sleep(5)
            if cache_key in ongoing_analyses:
                del ongoing_analyses[cache_key]
        
        # Run cleanup in background
        asyncio.create_task(cleanup())


async def analyze_token(
    token_address: str,
    chain: str = None,
    token_symbol: str = None,
    analyze_for_trading: bool = False,
    auto_execute: bool = False,
    input_token: str = "SOL",
    portfolio_percent: float = None
) -> Dict[str, Any]:
    """
    Main analysis function that coordinates data fetching and agency processing
    
    NOTE: Use analyze_token_with_cache() instead for automatic caching and deduplication

    Args:
        token_address: Contract address of the token
        chain: Blockchain name (required)
        token_symbol: Token symbol (extracted from market data if not provided)

    Returns:
        Dict containing the complete analysis results
    """

    if not chain:
        raise ValueError("Chain parameter is required")

    # Step 1: Fetch external data before agency initialization
    try:
        external_data = await fetch_all_token_data(token_address, chain)

        # Use symbol from market data if not provided
        if not token_symbol:
            token_symbol = external_data["token_symbol"]
            print(f"📊 ${token_symbol}")

        # Store trading parameters separately for post-agency analysis
        trading_params = {
            "analyze_for_trading": analyze_for_trading,
            "auto_execute": auto_execute,
            "input_token": input_token,
            "portfolio_percent": portfolio_percent
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to fetch external data: {str(e)}",
            "data": None,
        }

    # Step 2: Prepare result data (no agency - using Grok sentiment from data fetchers)
    result_data = {
        "token_info": {
            "name": external_data["token_name"],
            "symbol": token_symbol,
            "address": token_address,
            "chain": chain,
        },
        "market_data": external_data["market_data"],
        "holder_data": external_data["holder_data"],
        "bundler_analysis": external_data.get("bundler_analysis"),
        "market_health_24h": external_data.get("market_health_24h"),
        "safety_analysis": external_data.get("safety_analysis"),
        "sentiment_data": external_data.get("sentiment_data"),
        "trading_decision": None,
        "trading_params": trading_params
    }

    # Generate formatted analysis for backwards compatibility with telegram/twitter handlers
    result_data["analysis_response"] = format_token_report(result_data)

    return {
        "success": True,
        "data": result_data,
        "error": None,
    }


async def search_for_tokens(
    keyword: str, search_by: str = "symbol", limit: int = 20
) -> Dict[str, Any]:
    """
    Search for tokens by symbol, name, or address

    Args:
        keyword: Search term
        search_by: Search criteria ("symbol", "name", or "address")
        limit: Maximum number of results

    Returns:
        Dict containing search results or error
    """
    try:
        results = await search_tokens(keyword, search_by, limit)

        if not results:
            return {
                "success": False,
                "message": f"No verified tokens found for '{keyword}' on supported chains",
                "results": []
            }

        return {
            "success": True,
            "message": f"Found {len(results)} verified token(s)",
            "results": results
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Search failed: {str(e)}",
            "results": []
        }


def check_environment(include_twitter: bool = False) -> bool:
    """Verify required environment variables are set"""

    required_vars = ["OPENAI_API_KEY", "XAI_API_KEY", "BIRDEYE_API_KEY"]
    optional_vars = ["TWEET_SCOUT_ID", "MORALIS_API_KEY"]

    twitter_vars = [
        "TWITTER_API_KEY",
        "TWITTER_API_KEY_SECRET",
        "TWITTER_ACCESS_TOKEN",
        "TWITTER_ACCESS_TOKEN_SECRET"
    ]

    if include_twitter:
        optional_vars.extend(twitter_vars)

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
        print("Please check your .env file")
        return False

    print("✅ Environment check passed")
    return True


# API Endpoints
@app.get("/")
async def root():
    """Root endpoint for health checks"""
    endpoints = ["/api/extract-token", "/webhook/telegram", "/docs"]
    if token_list_router is not None:
        endpoints.extend([
            "/token-list/fetch",
            "/token-list/presets",
            "/token-list/jobs/create",
            "/token-list/jobs/list"
        ])

    return {
        "service": "GoArlo Crypto Analysis API",
        "status": "healthy",
        "version": "1.0.0",
        "endpoints": endpoints,
        "features": {
            "token_analysis": True,
            "telegram_bot": telegram_handler is not None,
            "token_list_api": token_list_router is not None
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "goarlo-api"}

@app.post("/api/extract-token", response_model=TokenAnalysisResponse)
@limiter.limit("20/minute")
async def extract_token_from_text(
    request: Request,
    req_data: TextAnalysisRequest = Body(...),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """Extract token, perform analysis, and post Twitter reply (rate limited)"""
    if x_api_key:
        expected_key = os.getenv("APP_TOKEN")
        if expected_key and x_api_key != expected_key:
            raise HTTPException(status_code=401, detail="Invalid API key")
    
    try:
        address_pattern = r'\b[a-zA-Z0-9]{32,44}\b'
        address_matches = re.findall(address_pattern, req_data.text)

        if address_matches:
            contract_address = address_matches[0]
            search_results = await search_tokens(
                keyword=contract_address,
                search_by="address",
                limit=10
            )

            if not search_results:
                return TokenAnalysisResponse(
                    success=False,
                    message=f"No token found for address: {contract_address}",
                    token_data=None,
                    analysis_data=None,
                    twitter_data=None
                )

            token_data = search_results[0]
        else:
            cashtag_pattern = r'\$([A-Za-z0-9]+)(?=[\s.,!?]|$)'
            cashtag_matches = re.findall(cashtag_pattern, req_data.text)

            if not cashtag_matches:
                return TokenAnalysisResponse(
                    success=False,
                    message="No valid contract address or symbol found in text",
                    token_data=None,
                    analysis_data=None,
                    twitter_data=None
                )

            token_symbol = cashtag_matches[0]
            search_results = await search_tokens(
                keyword=token_symbol,
                search_by="symbol",
                limit=10
            )

            if not search_results:
                return TokenAnalysisResponse(
                    success=False,
                    message=f"No token found for symbol: ${token_symbol}",
                    token_data=None,
                    analysis_data=None,
                    twitter_data=None
                )

            token_data = search_results[0]
            for result in search_results:
                if result.symbol.upper() == token_symbol.upper():
                    token_data = result
                    break

        # Step 1: Prepare token data
        token_response_data = {
            "symbol": token_data.symbol,
            "address": token_data.address,
            "chain": token_data.network,
            "name": token_data.name,
            "link": req_data.link,
            "price": token_data.price,
            "market_cap": token_data.market_cap,
            "volume_24h": token_data.volume_24h_usd,
            "verified": token_data.verified
        }

        # Step 2: Perform token analysis
        try:
            print(f"🤖 Starting analysis for {token_data.name} (${token_data.symbol})")
            analysis_result = await analyze_token_with_cache(
                token_address=token_data.address,
                chain=token_data.network,
                token_symbol=token_data.symbol
            )

            if not analysis_result["success"]:
                return TokenAnalysisResponse(
                    success=False,
                    message=f"Analysis failed: {analysis_result.get('error', 'Unknown error')}",
                    token_data=token_response_data,
                    analysis_data=None,
                    twitter_data=None
                )

            print(f"✅ Analysis completed for ${token_data.symbol}")

        except Exception as e:
            print(f"❌ Analysis failed: {str(e)}")
            return TokenAnalysisResponse(
                success=False,
                message=f"Analysis failed: {str(e)}",
                token_data=token_response_data,
                analysis_data=None,
                twitter_data=None
            )

        # Step 3: Extract tweet ID and post Twitter reply
        twitter_result = {"success": False, "error": "No tweet ID found"}

        tweet_id = extract_tweet_id(req_data.link)
        if tweet_id:
            try:
                print(f"🐦 Posting Twitter reply to tweet {tweet_id}")
                twitter_result = await post_twitter_reply(
                    data=analysis_result["data"],
                    reply_to_tweet=tweet_id
                )

                if twitter_result["success"]:
                    print(f"✅ Successfully posted Twitter reply")
                else:
                    print(f"❌ Failed to post Twitter reply: {twitter_result.get('error')}")

            except Exception as e:
                print(f"❌ Twitter posting failed: {str(e)}")
                twitter_result = {"success": False, "error": str(e)}
        else:
            print(f"⚠️  Could not extract tweet ID from URL: {req_data.link}")
            twitter_result = {"success": False, "error": "Invalid Twitter URL format"}

        return TokenAnalysisResponse(
            success=True,
            message=f"Complete analysis for {token_data.name} (${token_data.symbol})",
            token_data=token_response_data,
            analysis_data=analysis_result["data"],
            twitter_data=twitter_result
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing text: {str(e)}"
        )


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Telegram webhook endpoint for processing bot mentions.

    Handles incoming Telegram messages, parses token addresses/symbols,
    performs analysis, and sends formatted responses.
    """
    try:
        if telegram_handler is None:
            print("Telegram handler not initialized (missing TELEGRAM_BOT_TOKEN)")
            return {"ok": True}
        return await telegram_handler.process_webhook(request)
    except Exception as e:
        print(f"Error in Telegram webhook: {str(e)}")
        return {"ok": True}


async def execute_trade_direct(
    token_address: str,
    structured_data: Dict[str, Any],
    input_token: str = "SOL",
    portfolio_percent: float = 10.0
) -> Optional[Dict[str, Any]]:
    """
    Execute trade using direct imports (no HTTP calls)

    Args:
        token_address: Output token address
        structured_data: Token data from fetch_all_token_data
        input_token: Input token symbol (default SOL)
        portfolio_percent: Percentage of input token balance to use

    Returns:
        Execution result dict or None if failed
    """
    try:
        from trading_tools import AutoExecuteSwap
        from wallet_fetcher import get_sol_balance

        sol_balance = get_sol_balance() or 0
        if sol_balance <= 0.01:
            print(f"❌ Insufficient SOL balance: {sol_balance:.6f}")
            return {"action_taken": "FAILED", "reason": "Insufficient SOL balance"}

        max_amount = float(os.getenv("MAX_AMOUNT", "0.1"))
        available = max(0, sol_balance - 0.01)  # Reserve for fees
        swap_amount = min((portfolio_percent / 100.0) * available, max_amount)

        if swap_amount <= 0:
            return {"action_taken": "FAILED", "reason": "Calculated swap amount is zero"}

        token_info = structured_data.get("token_info", {})
        symbol = token_info.get("symbol", "UNKNOWN")

        print(f"💰 Executing trade: {swap_amount:.6f} SOL → ${symbol}")

        swap = AutoExecuteSwap(
            message_content=f"BUY ${symbol} on Solana",
            input_token=input_token,
            token_address=token_address
        )
        result = swap.run()

        if result and "❌" not in result:
            print(f"✅ Trade executed successfully")
            return {
                "action_taken": "EXECUTED",
                "result": result,
                "swap_details": {
                    "token_address": token_address,
                    "token_symbol": symbol,
                    "amount_sol": swap_amount
                }
            }
        else:
            print(f"❌ Trade failed: {result}")
            return {"action_taken": "FAILED", "reason": result}

    except ImportError as e:
        print(f"❌ Trading tools not available: {e}")
        return {"action_taken": "FAILED", "reason": "Trading tools not available"}
    except Exception as e:
        print(f"❌ Trade execution error: {e}")
        return {"action_taken": "FAILED", "reason": str(e)}


async def main():
    """Main CLI interface"""

    parser = argparse.ArgumentParser(
        description="GoArlo Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Token Analysis
  python main.py --address So11111111111111111111111111111111111111112 --chain solana
  python main.py --address 0x1234... --chain ethereum --symbol ETH
  python main.py --address 0x7109cb91f05E567E4164cd0bA692033198f39B2A --chain bnb
  python main.py --address 0x11dC28D01984079b7efE7763b533e6ed9E3722B9 --chain base

  # Token Search
  python main.py --search ARLO --search-by symbol
  python main.py --search "Solana" --search-by name --search-limit 5
  python main.py --search 0x1234567890abcdef --search-by address

  # Twitter Integration
  python main.py --address <ADDRESS> --chain <CHAIN> --preview-tweet
  python main.py --address <ADDRESS> --chain <CHAIN> --reply-to-tweet 1234567890

  # Trading Analysis
  python main.py --address <ADDRESS> --chain <CHAIN> --analyze-for-trading
  python main.py --address <ADDRESS> --chain <CHAIN> --analyze-for-trading --auto-execute
  python main.py --address <ADDRESS> --chain <CHAIN> --analyze-for-trading --auto-execute --input-token USDC
  python main.py --address <ADDRESS> --chain <CHAIN> --analyze-for-trading --auto-execute --portfolio-percent 10
        """,
    )

    token_group = parser.add_mutually_exclusive_group(required=True)
    token_group.add_argument("--address", help="Token contract address")
    token_group.add_argument("--search", help="Search for tokens by symbol, name, or address")
    token_group.add_argument("--momentum", action="store_true", help="Fetch and analyze top momentum tokens")

    parser.add_argument(
        "--chain", help="Blockchain (solana, ethereum, base, bnb, shibarium)"
    )
    parser.add_argument("--symbol", help="Token symbol (auto-detected if not provided)")
    parser.add_argument(
        "--search-by",
        choices=["symbol", "name", "address"],
        default="symbol",
        help="Search criteria when using --search (default: symbol)"
    )
    parser.add_argument(
        "--search-limit",
        type=int,
        default=10,
        help="Maximum number of search results (default: 10, max: 20)"
    )
    parser.add_argument(
        "--reply-to-tweet", help="Tweet ID to reply to with analysis results"
    )
    parser.add_argument(
        "--preview-tweet", action="store_true", help="Preview tweet format without posting"
    )
    parser.add_argument(
        "--analyze-for-trading", action="store_true", help="Analyze token report for trading decisions"
    )
    parser.add_argument(
        "--auto-execute", action="store_true", help="Auto-execute trades if analysis recommends BUY"
    )
    parser.add_argument(
        "--input-token", default="SOL", help="Input token for trading (default: SOL)"
    )
    parser.add_argument(
        "--portfolio-percent",
        type=float,
        help="Percentage of input token balance to use for trade (e.g., 10 = use 10%% of SOL balance)"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear analysis cache before running"
    )

    # Momentum trading options
    parser.add_argument(
        "--risk-profile",
        choices=["strict", "conservative", "moderate", "aggressive"],
        default="strict",
        help="Trading risk profile for --momentum (default: strict - safest)"
    )

    args = parser.parse_args()

    if args.clear_cache:
        analysis_cache.clear()
        ongoing_analyses.clear()
        print("🧹 Cleared analysis cache")
        if not (args.address or args.search):
            print("Cache cleared successfully!")
            return

    print("🚀 GoArlo Crypto Summary Bot")
    print("=" * 40)

    include_twitter = bool(args.reply_to_tweet or args.preview_tweet)
    if not check_environment(include_twitter=include_twitter):
        return

    try:
        if args.search:
            from token_search import search_tokens, display_search_results

            print(f"\n🔍 Searching for tokens: '{args.search}' (by {args.search_by})")
            print("=" * 60)

            search_results = await search_tokens(
                keyword=args.search,
                search_by=args.search_by,
                limit=min(args.search_limit, 20)  # Cap at 20
            )

            if search_results:
                search_result = {
                    "success": True,
                    "message": f"Found {len(search_results)} verified token(s) on supported chains",
                    "results": search_results
                }
            else:
                search_result = {
                    "success": False,
                    "message": "No verified tokens found on supported chains",
                    "results": []
                }

            display_search_results(search_result)
            return

        elif args.momentum:
            from trading_system import ComprehensiveTradingSystem

            system = ComprehensiveTradingSystem(
                dry_run=not args.auto_execute,
                risk_profile=args.risk_profile,
                enable_auto_sell=False,
                max_trade_amount=args.portfolio_percent / 100 if args.portfolio_percent else None
            )

            await system.run(cycles=1, interval_minutes=1)
            return

        if args.address and not args.chain:
            print("❌ Error: --chain is required when using --address")
            print("Example: python main.py --address <ADDRESS> --chain solana")
            return

        # Run analysis for specific token address
        result = await analyze_token_with_cache(
            token_address=args.address,
            chain=args.chain,
            token_symbol=args.symbol,
            analyze_for_trading=args.analyze_for_trading,
            auto_execute=args.auto_execute,
            input_token=args.input_token,
            portfolio_percent=args.portfolio_percent
        )

        if result["success"]:
            formatted_output = format_token_report(result["data"])
            print(formatted_output)

            if result["data"].get("trading_params", {}).get("analyze_for_trading"):
                print("\n🔍 Running trading analysis...")

                analyzer = TradingAnalyzer(criteria=get_conservative_criteria())
                recommendation = analyzer.analyze_structured_data(result["data"])

                trading_result = {
                    "action": recommendation.action,
                    "confidence": recommendation.confidence,
                    "position_size_percent": recommendation.position_size_percent,
                    "reasoning": recommendation.reasoning,
                    "risk_factors": recommendation.risk_factors,
                    "criteria_results": recommendation.criteria_met
                }

                print(f"🎯 Trading Analysis Complete:")
                print(f"  Action: {trading_result['action']}")
                print(f"  Confidence: {trading_result['confidence']:.1%}")

                # Auto-execute if requested and action is BUY
                if result["data"]["trading_params"].get("auto_execute") and trading_result["action"] == "BUY":
                    print("🚀 Auto-executing trade...")
                    execution_result = await execute_trade_direct(
                        token_address=args.address,
                        structured_data=result["data"],
                        input_token=result["data"]["trading_params"].get("input_token", "SOL"),
                        portfolio_percent=result["data"]["trading_params"].get("portfolio_percent", 10.0)
                    )
                    if execution_result:
                        trading_result["execution"] = execution_result

                result["data"]["trading_decision"] = trading_result

            if result["data"].get("trading_decision"):
                trading = result["data"]["trading_decision"]
                print("\n" + "=" * 60)
                print("🎯 TRADING ANALYSIS")
                print("=" * 60)

                if isinstance(trading, dict):
                    print(f"📊 Action: {trading.get('action', 'N/A')}")
                    print(f"🎯 Confidence: {trading.get('confidence', 0):.1%}")

                    if trading.get('position_size_percent'):
                        print(f"📈 Position Size: {trading.get('position_size_percent'):.1f}%")

                    if trading.get('reasoning'):
                        print(f"\n✅ Positive Factors:")
                        for reason in trading.get('reasoning', []):
                            print(f"  • {reason}")

                    if trading.get('risk_factors'):
                        print(f"\n⚠️  Risk Factors:")
                        for risk in trading.get('risk_factors', []):
                            print(f"  • {risk}")

                    print(f"\n💰 Trade Execution:")
                    if trading.get('execution'):
                        execution = trading['execution']
                        print(f"  Status: {execution.get('action_taken', 'N/A')}")
                        if execution.get('execution_result'):
                            print(f"  Result: {execution.get('execution_result')}")
                    else:
                        auto_execute_requested = result["data"]["trading_params"].get("auto_execute", False)
                        action_is_buy = trading.get("action") == "BUY"

                        if auto_execute_requested and action_is_buy:
                            print(f"  Status: FAILED (execution not completed)")
                        elif auto_execute_requested and not action_is_buy:
                            print(f"  Status: SKIPPED (action was {trading.get('action', 'N/A')}, not BUY)")
                        else:
                            print(f"  Status: DISABLED (auto-execute not requested)")
                else:
                    print(trading)

                print("=" * 60)

            if args.preview_tweet or args.reply_to_tweet:
                print("\n🐦 Twitter Integration:")
                if args.preview_tweet:
                    preview_tweet_format(result["data"])

                if args.reply_to_tweet:
                    twitter_result = await post_twitter_reply(
                        data=result["data"],
                        reply_to_tweet=args.reply_to_tweet
                    )

                    if twitter_result["success"]:
                        print(f"✅ Successfully posted reply to tweet {args.reply_to_tweet}")
                        if twitter_result.get("tweet_content"):
                            print(f"📝 Posted content ({len(twitter_result['tweet_content'])} chars):")
                            print(f"   {twitter_result['tweet_content'][:100]}{'...' if len(twitter_result['tweet_content']) > 100 else ''}")
                    else:
                        print(f"❌ Failed to post reply to tweet {args.reply_to_tweet}")
                        if twitter_result.get("error"):
                            print(f"   Error: {twitter_result['error']}")

        else:
            print(f"\n❌ Analysis Failed: {result['error']}")

    except KeyboardInterrupt:
        print("\n\n⚠️  Analysis interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    is_cli_mode = len(sys.argv) > 1 and sys.argv[1] == "--cli"

    if is_cli_mode:
        sys.argv.pop(1)
        asyncio.run(main())
    else:
        import uvicorn

        port = int(os.getenv("PORT", 8000))

        print("🚀 Starting GoArlo API Server...")
        print(f"🌐 Running on port {port}")

        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=port,
            reload=False
        )
