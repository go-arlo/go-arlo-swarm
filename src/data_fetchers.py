"""
Data fetching utilities for external APIs
Handles BirdEye and Moralis API calls before agency initialization
"""

import os
import aiohttp
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Optional, Dict, Any, Union, List, Tuple
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Supported chains for token analysis
SUPPORTED_CHAINS = ["solana", "ethereum", "base", "bsc", "shibarium"]

class TokenMarketData(BaseModel):
    """Market data from BirdEye API"""

    price_usd: float
    fdv_usd: float
    market_cap_usd: Optional[float]
    volume_24h_usd: float
    liquidity_usd: float
    price_change_24h_percent: Optional[float]
    price_change_1h_percent: Optional[float]
    token_symbol: str
    token_name: str
    ohlcv_5m: Optional[Dict[str, Any]]  # 5-minute OHLCV data


class TokenHolderData(BaseModel):
    """Holder data from Moralis API"""

    total_holders: int
    top10_concentration: Optional[float]
    holder_change_24h: Optional[int]
    chain: str


class BundleCluster(BaseModel):
    """Represents a cluster of bundled transactions"""

    cluster_size: int
    window_seconds: float
    unique_wallets: int
    wallet_diversity_ratio: float
    score: float
    sample_txs: List[str]
    first_unix: int


class CreationInfo(BaseModel):
    """Token creation information from BirdEye"""

    created_at: str  # ISO format timestamp
    creation_tx: str  # Transaction hash
    block_unix_time: int


class BundleRiskMetrics(BaseModel):
    """Risk assessment metrics for bundled activity"""

    bundle_intensity_score: float  # 0-100 scale based on cluster frequency and size
    wallet_concentration_risk: float  # 0-1 scale, higher = more concentrated
    bundle_timing_consistency: float  # 0-1 scale, higher = more coordinated timing
    early_trading_dominance: float  # Percentage of first 300 transactions that were bundled
    coordination_sophistication: str  # "LOW", "MEDIUM", "HIGH" based on patterns


class BundlerAnalysis(BaseModel):
    """Complete bundler analysis results for a token"""

    bundled_detected: bool
    bundle_cluster_count: int
    bundle_clusters: List[BundleCluster]
    creation_info: Optional[CreationInfo]
    risk_metrics: Optional[BundleRiskMetrics]  # Risk assessment instead of supply percentage
    total_bundled_tokens: Optional[float]  # Total tokens in bundled transactions
    present_impact_analysis: Optional[Dict[str, Any]]  # Current holdings analysis
    price_action_analysis: Optional[Dict[str, Any]]  # OHLCV-based sell-off analysis
    meta: Dict[str, Any]



def safe_float(value: Union[str, int, float, None], default: float = 0.0) -> float:
    """
    Safely convert a value to float, handling None and invalid values.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def iso_timestamp(unix_ts: int) -> str:
    """Convert unix timestamp to ISO format string"""
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()




async def fetch_ohlcv_data(
    token_address: str,
    time_from: int,
    time_to: int,
    chain: str = "solana",
    timeframe: str = "1D"
) -> List[Dict[str, Any]]:
    """
    Fetch OHLCV data from BirdEye API for price action analysis.

    Args:
        token_address: Token address
        time_from: Unix timestamp start time
        time_to: Unix timestamp end time
        chain: Blockchain (solana, ethereum, base, bsc, etc.)
        timeframe: Timeframe for candles (1D, 4H, 1H, 15m, etc.)

    Returns:
        List of OHLCV candle data
    """
    api_key = os.getenv("BIRDEYE_API_KEY")
    if not api_key:
        print("⚠️  BIRDEYE_API_KEY not set - skipping OHLCV analysis")
        return []

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
        "Accept": "application/json"
    }

    url = f"{base_url}/defi/v3/ohlcv"
    params = {
        "address": token_address,
        "type": timeframe,
        "currency": "usd",
        "time_from": time_from,
        "time_to": time_to,
        "ui_amount_mode": "raw"
    }

    print(f"📊 Fetching OHLCV data for price action analysis...")
    print(f"   Time range: {datetime.fromtimestamp(time_from)} to {datetime.fromtimestamp(time_to)}")
    print(f"   Timeframe: {timeframe}")

    async with aiohttp.ClientSession() as session:
        # Add rate limiting
        await asyncio.sleep(0.2)

        try:
            async with session.get(url, headers=headers, params=params, timeout=30) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"⚠️  BirdEye OHLCV API error: {response.status} - {error_text}")
                    return []

                data = await response.json()

                if not data.get("success") or not data.get("data", {}).get("items"):
                    print(f"⚠️  No OHLCV data available for this token")
                    return []

                items = data["data"]["items"]
                print(f"✅ Fetched {len(items)} OHLCV candles")

                return items

        except Exception as e:
            print(f"❌ Error fetching OHLCV data: {str(e)}")
            return []


def analyze_price_action_selloff(
    ohlcv_data: List[Dict[str, Any]],
    bundle_start_time: int
) -> Dict[str, Any]:
    """
    Analyze OHLCV data to detect major sell-offs that might indicate bundled tokens were dumped.

    Args:
        ohlcv_data: List of OHLCV candles from BirdEye
        bundle_start_time: Unix timestamp when bundling occurred

    Returns:
        Dictionary with sell-off analysis results
    """
    if not ohlcv_data or len(ohlcv_data) < 2:
        return {
            "selloff_detected": False,
            "selloff_severity": "UNKNOWN",
            "analysis_note": "Insufficient OHLCV data for price action analysis",
            "data_points": 0
        }

    # Sort candles by time
    sorted_candles = sorted(ohlcv_data, key=lambda x: x.get("unix_time", 0))

    # Extract price data
    highs = [safe_float(candle.get("h", 0)) for candle in sorted_candles]
    lows = [safe_float(candle.get("l", 0)) for candle in sorted_candles]
    opens = [safe_float(candle.get("o", 0)) for candle in sorted_candles]
    closes = [safe_float(candle.get("c", 0)) for candle in sorted_candles]
    volumes = [safe_float(candle.get("v_usd", 0)) for candle in sorted_candles]

    if not highs or max(highs) == 0:
        return {
            "selloff_detected": False,
            "selloff_severity": "UNKNOWN",
            "analysis_note": "No valid price data found",
            "data_points": len(sorted_candles)
        }

    # Calculate key metrics
    peak_price = max(highs)
    peak_index = highs.index(peak_price)
    current_price = closes[-1] if closes else 0

    # Calculate price decline from peak
    price_decline_pct = ((peak_price - current_price) / peak_price * 100) if peak_price > 0 else 0

    # Calculate volatility (high-low ranges)
    daily_ranges = []
    for i, candle in enumerate(sorted_candles):
        high = highs[i]
        low = lows[i]
        if high > 0 and low > 0:
            daily_range_pct = ((high - low) / low * 100)
            daily_ranges.append(daily_range_pct)

    avg_volatility = sum(daily_ranges) / len(daily_ranges) if daily_ranges else 0
    max_volatility = max(daily_ranges) if daily_ranges else 0

    # Detect large single-day drops
    large_drops = []
    for i in range(1, len(closes)):
        if closes[i-1] > 0:
            daily_change = ((closes[i] - closes[i-1]) / closes[i-1] * 100)
            if daily_change < -20:  # More than 20% drop in a day
                large_drops.append({
                    "day": i,
                    "drop_percent": abs(daily_change),
                    "unix_time": sorted_candles[i].get("unix_time", 0)
                })

    # Volume analysis - detect high volume sell-offs
    if volumes and len(volumes) > 1:
        avg_volume = sum(volumes) / len(volumes)
        high_volume_days = [
            {
                "day": i,
                "volume_multiple": volumes[i] / avg_volume if avg_volume > 0 else 0,
                "price_change": ((closes[i] - opens[i]) / opens[i] * 100) if opens[i] > 0 else 0
            }
            for i in range(len(volumes))
            if volumes[i] > avg_volume * 2  # More than 2x average volume
        ]
    else:
        high_volume_days = []

    # Determine sell-off severity
    selloff_severity = "NONE"
    selloff_detected = False
    risk_factors = []

    if price_decline_pct > 80:
        selloff_severity = "EXTREME"
        selloff_detected = True
        risk_factors.append(f"Extreme price decline from peak ({price_decline_pct:.1f}%)")
    elif price_decline_pct > 60:
        selloff_severity = "SEVERE"
        selloff_detected = True
        risk_factors.append(f"Severe price decline from peak ({price_decline_pct:.1f}%)")
    elif price_decline_pct > 40:
        selloff_severity = "MODERATE"
        selloff_detected = True
        risk_factors.append(f"Moderate price decline from peak ({price_decline_pct:.1f}%)")
    elif price_decline_pct > 20:
        selloff_severity = "MILD"
        selloff_detected = True
        risk_factors.append(f"Mild price decline from peak ({price_decline_pct:.1f}%)")

    if len(large_drops) > 0:
        selloff_detected = True
        risk_factors.append(f"{len(large_drops)} large single-day drops detected")

    if len(high_volume_days) > 0:
        high_vol_selloffs = [day for day in high_volume_days if day["price_change"] < -10]
        if high_vol_selloffs:
            risk_factors.append(f"{len(high_vol_selloffs)} high-volume sell-off days")

    # Risk mitigation assessment
    mitigation_factor = "NONE"
    if selloff_detected:
        if selloff_severity in ["EXTREME", "SEVERE"]:
            mitigation_factor = "HIGH"  # Major selloff likely dumped bundled tokens
        elif selloff_severity == "MODERATE":
            mitigation_factor = "MEDIUM"
        else:
            mitigation_factor = "LOW"

    return {
        "selloff_detected": selloff_detected,
        "selloff_severity": selloff_severity,
        "price_decline_from_peak_pct": round(price_decline_pct, 1),
        "peak_price": peak_price,
        "current_price": current_price,
        "large_drops_count": len(large_drops),
        "large_drops": large_drops,
        "high_volume_selloffs": len([day for day in high_volume_days if day["price_change"] < -10]),
        "avg_daily_volatility_pct": round(avg_volatility, 1),
        "max_daily_volatility_pct": round(max_volatility, 1),
        "risk_mitigation_factor": mitigation_factor,
        "risk_factors": risk_factors,
        "data_points": len(sorted_candles),
        "analysis_note": f"Price action analysis over {len(sorted_candles)} days shows {selloff_severity.lower()} sell-off patterns"
    }


async def analyze_24h_market_health(
    token_address: str,
    chain: str
) -> Dict[str, Any]:
    """
    Analyze 24-hour market health using OHLCV data for comprehensive market assessment.

    Args:
        token_address: Token contract address
        chain: Blockchain name

    Returns:
        Dictionary with 24h market health metrics
    """
    current_time = int(time.time())
    time_24h_ago = current_time - (24 * 60 * 60)  # 24 hours ago

    print(f"📊 Analyzing 24h market health for {chain}...")

    # Fetch 15-minute candles for detailed analysis
    ohlcv_data = await fetch_ohlcv_data(
        token_address,
        time_24h_ago,
        current_time,
        chain,
        timeframe="15m"
    )

    if not ohlcv_data or len(ohlcv_data) < 2:
        return {
            "market_health_available": False,
            "analysis_note": "Insufficient 24h OHLCV data for market health analysis",
            "data_points": len(ohlcv_data) if ohlcv_data else 0
        }

    # Sort candles by time
    sorted_candles = sorted(ohlcv_data, key=lambda x: x.get("unix_time", 0))

    # Extract price and volume data
    opens = [safe_float(candle.get("o", 0)) for candle in sorted_candles]
    highs = [safe_float(candle.get("h", 0)) for candle in sorted_candles]
    lows = [safe_float(candle.get("l", 0)) for candle in sorted_candles]
    closes = [safe_float(candle.get("c", 0)) for candle in sorted_candles]
    volumes = [safe_float(candle.get("v_usd", 0)) for candle in sorted_candles]

    if not closes or max(closes) == 0:
        return {
            "market_health_available": False,
            "analysis_note": "No valid price data in 24h window",
            "data_points": len(sorted_candles)
        }

    # Calculate 24h metrics
    h24_high = max(highs)
    h24_low = min(lows)
    current_price = closes[-1]
    start_price = opens[0]

    price_change_24h = ((current_price - start_price) / start_price * 100) if start_price > 0 else 0

    # Calculate buy/sell pressure using price action analysis
    buy_pressure_periods = 0
    sell_pressure_periods = 0
    neutral_periods = 0

    for i, candle in enumerate(sorted_candles):
        open_price = opens[i]
        close_price = closes[i]

        if close_price > open_price:
            # Green candle = buy pressure
            buy_pressure_periods += 1
        elif close_price < open_price:
            # Red candle = sell pressure
            sell_pressure_periods += 1
        else:
            neutral_periods += 1

    total_periods = len(sorted_candles)
    buy_pressure_pct = (buy_pressure_periods / total_periods * 100) if total_periods > 0 else 0
    sell_pressure_pct = (sell_pressure_periods / total_periods * 100) if total_periods > 0 else 0

    # Assess overall pressure dominance
    if buy_pressure_pct > 60:
        pressure_dominance = "STRONG_BUY"
    elif buy_pressure_pct > 55:
        pressure_dominance = "BUY"
    elif sell_pressure_pct > 60:
        pressure_dominance = "STRONG_SELL"
    elif sell_pressure_pct > 55:
        pressure_dominance = "SELL"
    else:
        pressure_dominance = "NEUTRAL"

    # Calculate volume metrics using actual OHLCV data
    total_volume = sum(volumes)
    avg_volume_per_period = total_volume / len(volumes) if volumes else 0

    # Calculate volatility for market health assessment
    volatility_periods = []
    for i in range(len(sorted_candles)):
        if highs[i] > 0 and lows[i] > 0:
            volatility = ((highs[i] - lows[i]) / lows[i] * 100)
            volatility_periods.append(volatility)

    avg_volatility = sum(volatility_periods) / len(volatility_periods) if volatility_periods else 0

    # Volume change analysis (compare first half vs second half of 24h)
    mid_point = len(volumes) // 2
    first_half_volume = sum(volumes[:mid_point]) if mid_point > 0 else 0
    second_half_volume = sum(volumes[mid_point:]) if mid_point < len(volumes) else 0

    volume_change = ((second_half_volume - first_half_volume) / first_half_volume * 100) if first_half_volume > 0 else 0

    # Market sentiment assessment
    sentiment_factors = []
    sentiment_score = 0

    # Price performance factor (40 points max)
    if price_change_24h > 10:
        sentiment_score += 40
        sentiment_factors.append(f"Strong price growth ({price_change_24h:+.1f}%)")
    elif price_change_24h > 5:
        sentiment_score += 25
        sentiment_factors.append(f"Positive price movement ({price_change_24h:+.1f}%)")
    elif price_change_24h > 0:
        sentiment_score += 15
        sentiment_factors.append(f"Slight price increase ({price_change_24h:+.1f}%)")
    elif price_change_24h > -5:
        sentiment_score += 5
        sentiment_factors.append(f"Minor price decline ({price_change_24h:+.1f}%)")
    else:
        sentiment_factors.append(f"Significant price decline ({price_change_24h:+.1f}%)")

    # Buy pressure factor (30 points max)
    if buy_pressure_pct > 65:
        sentiment_score += 30
        sentiment_factors.append(f"Dominant buy pressure ({buy_pressure_pct:.1f}%)")
    elif buy_pressure_pct > 55:
        sentiment_score += 20
        sentiment_factors.append(f"Strong buy pressure ({buy_pressure_pct:.1f}%)")
    elif buy_pressure_pct > 45:
        sentiment_score += 10
        sentiment_factors.append("Balanced buy/sell pressure")

    # Volume trend factor (20 points max)
    if volume_change > 50:
        sentiment_score += 20
        sentiment_factors.append(f"Increasing volume trend ({volume_change:+.1f}%)")
    elif volume_change > 0:
        sentiment_score += 10
        sentiment_factors.append(f"Growing volume ({volume_change:+.1f}%)")
    elif volume_change < -30:
        sentiment_factors.append(f"Declining volume ({volume_change:+.1f}%)")

    # Volatility assessment (10 points max)
    if avg_volatility < 5:
        sentiment_score += 10
        sentiment_factors.append("Low volatility (stable)")
    elif avg_volatility < 15:
        sentiment_score += 5
        sentiment_factors.append("Moderate volatility")
    else:
        sentiment_factors.append("High volatility")

    # Determine overall market health
    if sentiment_score >= 75:
        market_health = "EXCELLENT"
    elif sentiment_score >= 60:
        market_health = "GOOD"
    elif sentiment_score >= 45:
        market_health = "FAIR"
    else:
        market_health = "LOW"

    return {
        "market_health_available": True,
        "market_health": market_health,
        "sentiment_score": sentiment_score,
        "sentiment_factors": sentiment_factors,
        "price_change_24h_pct": round(price_change_24h, 2),
        "h24_high": h24_high,
        "h24_low": h24_low,
        "current_price": current_price,
        "buy_pressure_pct": round(buy_pressure_pct, 1),
        "sell_pressure_pct": round(sell_pressure_pct, 1),
        "pressure_dominance": pressure_dominance,
        "total_volume_24h_usd": round(total_volume, 2),
        "avg_volume_per_period_usd": round(avg_volume_per_period, 2),
        "volume_change_pct": round(volume_change, 1),
        "avg_volatility_pct": round(avg_volatility, 1),
        "data_points": len(sorted_candles),
        "analysis_note": f"24h market health: {market_health} based on {len(sorted_candles)} 15m candles"
    }


def coefficient_of_variation(values: List[float]) -> float:
    """Calculate coefficient of variation for a list of values"""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return (variance ** 0.5) / abs(mean)


def calculate_bundle_risk_metrics(
    bundle_clusters: List[BundleCluster],
    transactions: List[Dict[str, Any]],
    total_transactions_analyzed: int
) -> BundleRiskMetrics:
    """Calculate comprehensive risk metrics for bundled activity"""

    if not bundle_clusters or not transactions:
        return BundleRiskMetrics(
            bundle_intensity_score=0.0,
            wallet_concentration_risk=0.0,
            bundle_timing_consistency=0.0,
            early_trading_dominance=0.0,
            coordination_sophistication="LOW"
        )

    # 1. Bundle Intensity Score (0-100)
    # Based on: frequency of bundles, average cluster size, and bundle density
    total_bundled_txs = sum(cluster.cluster_size for cluster in bundle_clusters)
    bundle_frequency = len(bundle_clusters) / max(total_transactions_analyzed, 1)
    avg_cluster_size = total_bundled_txs / len(bundle_clusters)
    bundle_density = total_bundled_txs / max(total_transactions_analyzed, 1)

    intensity_score = min(100, (
        bundle_frequency * 200 +  # More frequent bundles = higher risk
        (avg_cluster_size - 3) * 10 +  # Larger clusters = higher risk
        bundle_density * 150  # Higher proportion bundled = higher risk
    ))

    # 2. Wallet Concentration Risk (0-1)
    # Analyze unique wallets across all bundles
    all_bundled_wallets = set()
    for cluster in bundle_clusters:
        # Extract wallets from sample transactions
        for tx_hash in cluster.sample_txs:
            # Find the transaction in our data
            for tx in transactions:
                if tx.get("tx_hash") == tx_hash:
                    wallet = tx.get("owner", "")
                    if wallet:
                        all_bundled_wallets.add(wallet)
                    break

    # Check for wallet reuse across different bundles
    wallet_appearances = {}
    for cluster in bundle_clusters:
        cluster_wallets = set()
        for tx_hash in cluster.sample_txs:
            for tx in transactions:
                if tx.get("tx_hash") == tx_hash:
                    wallet = tx.get("owner", "")
                    if wallet:
                        cluster_wallets.add(wallet)
                        wallet_appearances[wallet] = wallet_appearances.get(wallet, 0) + 1
                    break

    # Higher concentration = more wallets appearing in multiple bundles
    multi_bundle_wallets = sum(1 for count in wallet_appearances.values() if count > 1)
    concentration_risk = min(1.0, multi_bundle_wallets / max(len(all_bundled_wallets), 1))

    # 3. Bundle Timing Consistency (0-1)
    # Analyze how consistent the timing patterns are
    time_gaps = []
    sorted_clusters = sorted(bundle_clusters, key=lambda x: x.first_unix)
    for i in range(1, len(sorted_clusters)):
        gap = sorted_clusters[i].first_unix - sorted_clusters[i-1].first_unix
        time_gaps.append(gap)

    if time_gaps:
        timing_cv = coefficient_of_variation(time_gaps)
        # Lower coefficient of variation = more consistent timing = higher risk
        timing_consistency = max(0.0, 1.0 - min(1.0, timing_cv / 2.0))
    else:
        timing_consistency = 0.0

    # 4. Early Trading Dominance
    # What percentage of the first 300 transactions (or all available) were bundled?
    analysis_window = min(300, len(transactions))  # Analyze up to first 300
    early_txs = transactions[:analysis_window]

    # Track which transactions are bundled (by index to avoid double counting)
    bundled_indices = set()

    for i, tx in enumerate(early_txs):
        tx_time = tx.get("block_unix_time", 0)

        # Check if this transaction falls within any bundle cluster time window
        for cluster in bundle_clusters:
            cluster_start = cluster.first_unix
            cluster_end = cluster_start + cluster.window_seconds

            if cluster_start <= tx_time <= cluster_end:
                bundled_indices.add(i)
                break  # Don't count same transaction in multiple clusters

    early_bundled_count = len(bundled_indices)
    early_dominance = (early_bundled_count / len(early_txs)) * 100 if early_txs else 0.0

    # 5. Coordination Sophistication
    sophistication = "LOW"
    if intensity_score > 60 and concentration_risk > 0.5:
        sophistication = "HIGH"
    elif intensity_score > 30 or concentration_risk > 0.3:
        sophistication = "MEDIUM"

    return BundleRiskMetrics(
        bundle_intensity_score=round(intensity_score, 1),
        wallet_concentration_risk=round(concentration_risk, 3),
        bundle_timing_consistency=round(timing_consistency, 3),
        early_trading_dominance=round(early_dominance, 1),
        coordination_sophistication=sophistication
    )


async def analyze_present_impact(
    bundle_clusters: List[BundleCluster],
    transactions: List[Dict[str, Any]],
    token_address: str,
    chain: str
) -> Optional[Dict[str, Any]]:
    """Analyze present-day risk from bundled activity using multiple assessment methods"""

    # Extract all unique wallets that participated in bundles
    bundled_wallets = set()
    bundle_wallet_initial_buys = {}  # Track initial buy amounts

    for cluster in bundle_clusters:
        for tx_hash in cluster.sample_txs:
            for tx in transactions:
                if tx.get("tx_hash") == tx_hash:
                    wallet = tx.get("owner", "")
                    if wallet:
                        bundled_wallets.add(wallet)
                        # Track initial buy amount
                        to_data = tx.get("to", {})
                        if isinstance(to_data, dict):
                            amount = safe_float(to_data.get("ui_amount", 0))
                            bundle_wallet_initial_buys[wallet] = bundle_wallet_initial_buys.get(wallet, 0) + amount
                    break

    if not bundled_wallets:
        return None

    # Alternative Present Impact Assessment (independent of holder data)
    def calculate_bundle_pattern_risk():
        """Assess risk based on bundling patterns and sophistication"""
        risk_score = 0
        risk_factors = []

        bundle_count = len(bundle_clusters)
        total_bundled_txs = sum(cluster.cluster_size for cluster in bundle_clusters)

        # Minimum threshold: require meaningful bundle activity before scoring
        if bundle_count <= 3 and total_bundled_txs <= 15:
            risk_factors.append(f"Minimal bundle activity ({bundle_count} clusters, {total_bundled_txs} transactions)")
            return max(5, risk_score), risk_factors  # Cap at very low score for minimal activity

        # Factor 1: Bundle cluster volume (40 points max) - Adjusted to be less sensitive
        if bundle_count > 100:
            risk_score += 40
            risk_factors.append(f"Extreme bundle activity ({bundle_count} clusters)")
        elif bundle_count > 50:
            risk_score += 30
            risk_factors.append(f"Very high bundle activity ({bundle_count} clusters)")
        elif bundle_count > 25:
            risk_score += 20
            risk_factors.append(f"High bundle activity ({bundle_count} clusters)")
        elif bundle_count > 10:
            risk_score += 15
            risk_factors.append(f"Moderate bundle activity ({bundle_count} clusters)")
        elif bundle_count > 5:
            risk_score += 10
            risk_factors.append(f"Some bundle activity ({bundle_count} clusters)")
        elif bundle_count > 3:
            risk_score += 5
            risk_factors.append(f"Low bundle activity ({bundle_count} clusters)")
        # No points for 3 or fewer clusters

        # Factor 2: Wallet reuse across bundles (30 points max)
        wallet_bundle_count = {}
        for cluster in bundle_clusters:
            for tx_hash in cluster.sample_txs:
                for tx in transactions:
                    if tx.get("tx_hash") == tx_hash:
                        wallet = tx.get("owner", "")
                        if wallet:
                            wallet_bundle_count[wallet] = wallet_bundle_count.get(wallet, 0) + 1
                        break

        multi_bundle_wallets = sum(1 for count in wallet_bundle_count.values() if count > 1)
        if multi_bundle_wallets > len(bundled_wallets) * 0.5:
            risk_score += 30
            risk_factors.append("High wallet reuse across bundles (>50%)")
        elif multi_bundle_wallets > len(bundled_wallets) * 0.3:
            risk_score += 20
            risk_factors.append("Significant wallet reuse across bundles (>30%)")
        elif multi_bundle_wallets > 0:
            risk_score += 10
            risk_factors.append("Some wallet reuse detected")

        # Factor 3: Bundle size sophistication (20 points max) - More sophisticated threshold
        large_bundles = sum(1 for cluster in bundle_clusters if cluster.cluster_size > 15)
        very_large_bundles = sum(1 for cluster in bundle_clusters if cluster.cluster_size > 25)

        if very_large_bundles > 0:
            risk_score += 20
            risk_factors.append(f"Very large bundle clusters detected ({very_large_bundles} clusters >25 txs)")
        elif large_bundles > bundle_count * 0.4:
            risk_score += 15
            risk_factors.append("Many large bundle clusters (>15 transactions)")
        elif large_bundles > bundle_count * 0.2:
            risk_score += 10
            risk_factors.append("Some large bundle clusters detected")
        elif large_bundles > 0:
            risk_score += 5
            risk_factors.append("Few large bundle clusters")

        # Factor 4: Timing coordination (10 points max)
        if bundle_count > 5:
            time_gaps = []
            sorted_clusters = sorted(bundle_clusters, key=lambda x: x.first_unix)
            for i in range(1, len(sorted_clusters)):
                gap = sorted_clusters[i].first_unix - sorted_clusters[i-1].first_unix
                time_gaps.append(gap)

            if time_gaps:
                avg_gap = sum(time_gaps) / len(time_gaps)
                if avg_gap < 10:  # Very rapid succession
                    risk_score += 10
                    risk_factors.append("Rapid-fire bundle execution (<10s average)")
                elif avg_gap < 30:
                    risk_score += 5
                    risk_factors.append("Quick bundle succession (<30s average)")

        return risk_score, risk_factors

    # Calculate pattern-based risk
    pattern_risk_score, pattern_risk_factors = calculate_bundle_pattern_risk()

    # Determine overall risk level from pattern analysis - Adjusted thresholds
    if pattern_risk_score >= 80:
        pattern_risk_level = "CRITICAL"
    elif pattern_risk_score >= 60:
        pattern_risk_level = "HIGH"
    elif pattern_risk_score >= 35:
        pattern_risk_level = "MEDIUM"
    else:
        pattern_risk_level = "LOW"

    try:
        holder_data = await fetch_moralis_holder_data(chain, token_address)

        if holder_data:
            # Enhanced analysis with holder data
            total_holders = holder_data.total_holders
            bundled_wallet_percentage = (len(bundled_wallets) / total_holders) * 100 if total_holders > 0 else 0
            top10_concentration = holder_data.top10_concentration or 0
            holder_change_24h = holder_data.holder_change_24h or 0

            # Combine pattern risk with holder risk
            holder_risk_score = 0
            holder_risk_factors = []

            if bundled_wallet_percentage > 15:
                holder_risk_score += 30
                holder_risk_factors.append(f"High bundled wallet presence ({bundled_wallet_percentage:.1f}%)")
            elif bundled_wallet_percentage > 10:
                holder_risk_score += 20
                holder_risk_factors.append(f"Significant bundled wallet presence ({bundled_wallet_percentage:.1f}%)")

            if top10_concentration > 50:
                holder_risk_score += 20
                holder_risk_factors.append(f"Very high top-10 concentration ({top10_concentration:.1f}%)")

            if holder_change_24h and holder_change_24h < -10:
                holder_risk_score += 20
                holder_risk_factors.append("Significant holder exodus (>10% decrease)")

            # Final combined risk assessment
            combined_score = min(100, pattern_risk_score + holder_risk_score)

            if combined_score >= 80:
                final_risk = "CRITICAL"
            elif combined_score >= 60:
                final_risk = "HIGH"
            elif combined_score >= 40:
                final_risk = "MEDIUM"
            else:
                final_risk = "LOW"

            return {
                "bundled_wallets_count": len(bundled_wallets),
                "total_initial_tokens_bought": round(sum(bundle_wallet_initial_buys.values()), 2),
                "total_current_holders": total_holders,
                "bundled_wallet_penetration_percentage": round(bundled_wallet_percentage, 2),
                "top10_concentration": top10_concentration,
                "holder_change_24h": holder_change_24h,
                "current_impact_risk": final_risk,
                "pattern_risk_score": pattern_risk_score,
                "holder_risk_score": holder_risk_score,
                "combined_risk_score": combined_score,
                "pattern_risk_factors": pattern_risk_factors,
                "holder_risk_factors": holder_risk_factors,
                "analysis_method": "PATTERN_AND_HOLDER_DATA",
                "analysis_note": f"Combined Risk: {final_risk} (Pattern: {pattern_risk_score}, Holder: {holder_risk_score})"
            }
        else:
            # Pattern-only analysis when holder data unavailable
            return {
                "bundled_wallets_count": len(bundled_wallets),
                "total_initial_tokens_bought": round(sum(bundle_wallet_initial_buys.values()), 2),
                "current_impact_risk": pattern_risk_level,
                "pattern_risk_score": pattern_risk_score,
                "pattern_risk_factors": pattern_risk_factors,
                "analysis_method": "PATTERN_ONLY",
                "data_limitation": "Holder data unavailable",
                "analysis_note": f"Pattern-Based Risk: {pattern_risk_level} (Score: {pattern_risk_score}/100). Based on {len(bundle_clusters)} bundle clusters and {len(bundled_wallets)} unique bundled wallets."
            }

    except Exception as e:
        # Fallback to pattern-only analysis if there's any error
        pattern_risk_score, pattern_risk_factors = calculate_bundle_pattern_risk()

        if pattern_risk_score >= 80:
            pattern_risk_level = "CRITICAL"
        elif pattern_risk_score >= 60:
            pattern_risk_level = "HIGH"
        elif pattern_risk_score >= 35:
            pattern_risk_level = "MEDIUM"
        else:
            pattern_risk_level = "LOW"

        return {
            "bundled_wallets_count": len(bundled_wallets),
            "total_initial_tokens_bought": round(sum(bundle_wallet_initial_buys.values()), 2),
            "current_impact_risk": pattern_risk_level,
            "pattern_risk_score": pattern_risk_score,
            "pattern_risk_factors": pattern_risk_factors,
            "analysis_method": "PATTERN_ONLY_FALLBACK",
            "error_note": f"Holder data fetch failed: {str(e)}",
            "analysis_note": f"Pattern-Based Risk: {pattern_risk_level} (Score: {pattern_risk_score}/100). Fallback analysis due to data access issues."
        }


def detect_bundles(
    transactions: List[Dict[str, Any]],
    creation_ts: int,
    window_seconds: float = 2.0,
    min_trades_in_cluster: int = 3,
    max_wallet_diversity: float = 0.7
) -> Tuple[bool, List[BundleCluster], float]:
    """
    Detect bundled transactions in the first 300 transactions after token launch.

    Args:
        transactions: List of transaction data (should be first 300 from launch)
        creation_ts: Unix timestamp of token creation (if unreliable, uses earliest transaction)
        window_seconds: Time window to consider for clustering (default 2 seconds)
        min_trades_in_cluster: Minimum trades to qualify as a bundle (default 3)
        max_wallet_diversity: Maximum wallet diversity ratio for bundles (default 0.7)

    Returns:
        Tuple of (bundled_detected, list of BundleCluster objects, total_bundled_tokens)
    """
    if not transactions:
        return False, [], 0.0

    # Extract and sort all buy transactions by timestamp
    buy_txs = []
    for tx in transactions:
        tx_type = tx.get("tx_type") or tx.get("side", "")
        if tx_type == "buy":
            buy_txs.append(tx)

    if not buy_txs:
        return False, [], 0.0

    # Sort by timestamp ascending
    buy_txs.sort(key=lambda x: x.get("block_unix_time") or x.get("blockUnixTime", 0))

    # Determine effective launch time (for reference/logging only)
    earliest_tx_time = buy_txs[0].get("block_unix_time") or buy_txs[0].get("blockUnixTime", 0)

    # If creation_ts is far in the future or past compared to transactions, use earliest transaction
    if creation_ts and abs(creation_ts - earliest_tx_time) > 86400:  # More than 1 day difference
        effective_launch_time = earliest_tx_time
        print(f"⚠️  Using earliest transaction time as launch reference (creation_ts seems unreliable)")
    elif creation_ts:
        effective_launch_time = creation_ts
    else:
        effective_launch_time = earliest_tx_time

    # Use all fetched transactions (first 300 from launch), not filtered by time
    # This ensures we analyze the full early trading window regardless of how fast trading was
    txs_to_analyze = buy_txs
    
    print(f"🔍 Analyzing {len(txs_to_analyze)} transactions from launch (no time filtering)")

    if not txs_to_analyze:
        return False, [], 0.0

    bundles = []
    n = len(txs_to_analyze)
    i = 0

    while i < n:
        # Define window based on first transaction
        start_time = txs_to_analyze[i].get("block_unix_time") or txs_to_analyze[i].get("blockUnixTime", 0)
        window_end = start_time + window_seconds

        # Collect all transactions within window
        j = i
        while j < n:
            tx_time = txs_to_analyze[j].get("block_unix_time") or txs_to_analyze[j].get("blockUnixTime", 0)
            if tx_time <= window_end:
                j += 1
            else:
                break

        window_txs = txs_to_analyze[i:j]

        # Check if this qualifies as a cluster (minimum size check only)
        if len(window_txs) >= min_trades_in_cluster:
            # Extract wallet addresses
            wallets = []
            for tx in window_txs:
                wallet = tx.get("owner") or tx.get("user") or tx.get("wallet", "")
                if wallet:
                    wallets.append(wallet)

            # Calculate wallet diversity
            unique_wallets = len(set(wallets))
            wallet_diversity = unique_wallets / len(wallets) if wallets else 1.0

            # Calculate volumes for coherence check
            volumes = []
            for tx in window_txs:
                vol = safe_float(tx.get("volume_usd") or tx.get("volumeUsd", 0))
                if vol > 0:
                    volumes.append(vol)

            # Calculate price/volume coefficient of variation
            price_cv = coefficient_of_variation(volumes) if volumes else 0

            # Calculate bundle score (0-1 scale) - following reference implementation
            score = (
                0.5 * max(0, 1 - (len(window_txs) / min_trades_in_cluster - 1))
                + 0.3 * max(0, 1 - wallet_diversity / max_wallet_diversity)
                + 0.2 * max(0, 1 - price_cv / 0.2)
            )

            # Get sample transaction hashes
            sample_txs = []
            for tx in window_txs[:5]:  # Max 5 samples
                tx_hash = tx.get("tx_hash") or tx.get("txHash", "")
                if tx_hash:
                    sample_txs.append(tx_hash)

            # Create bundle cluster object - collect ALL clusters regardless of diversity
            cluster = BundleCluster(
                cluster_size=len(window_txs),
                window_seconds=window_seconds,
                unique_wallets=unique_wallets,
                wallet_diversity_ratio=round(wallet_diversity, 3),
                score=round(score, 3),
                sample_txs=sample_txs,
                first_unix=start_time
            )

            bundles.append(cluster)

        # Move to next transaction
        i += 1

    # Filter bundles based on criteria (following reference approach)
    # Keep clusters that meet diversity criteria OR have high scores
    valid_bundles = []
    for bundle in bundles:
        if bundle.wallet_diversity_ratio <= max_wallet_diversity or bundle.score >= 0.5:
            valid_bundles.append(bundle)

    # Calculate total tokens bundled from all valid bundles
    total_bundled_tokens = 0.0
    processed_indices = set()

    for bundle in valid_bundles:
        # Find transactions that belong to this bundle
        start_time = bundle.first_unix
        end_time = start_time + bundle.window_seconds

        for idx, tx in enumerate(txs_to_analyze):
            tx_time = tx.get("block_unix_time") or tx.get("blockUnixTime", 0)
            if start_time <= tx_time <= end_time and idx not in processed_indices:
                # Extract token amount from 'to' field (tokens received)
                to_data = tx.get("to", {})
                if isinstance(to_data, dict):
                    ui_amount = safe_float(to_data.get("ui_amount", 0))
                    total_bundled_tokens += ui_amount
                    processed_indices.add(idx)

    return (len(valid_bundles) > 0), valid_bundles, total_bundled_tokens


def detect_chain(address: str) -> str:
    """Auto-detect chain based on address format"""
    if address.startswith("0x") and len(address) == 42:
        return "base"  # Default EVM chain for 0x addresses
    elif len(address) in [32, 43, 44] and address.isalnum():
        return "solana"
    else:
        # Default to solana for other formats
        return "solana"


async def fetch_birdeye_market_data(chain: str, token_address: str) -> TokenMarketData:
    """Fetch comprehensive market data from BirdEye API"""

    api_key = os.getenv("BIRDEYE_API_KEY")
    if not api_key:
        raise Exception("BIRDEYE_API_KEY not found in environment variables. Please set it in your .env file")

    # Map our chain names to BirdEye's expected values
    chain_map = {
        "solana": "solana",
        "ethereum": "ethereum",
        "base": "base",
        "bnb": "bsc",
        "shibarium": "shibarium",
    }

    birdeye_chain = chain_map.get(chain.lower(), chain.lower())

    print(f"🦅 Fetching market data from BirdEye for {token_address} on {birdeye_chain}")

    base_url = "https://public-api.birdeye.so"
    headers = {
        "X-API-KEY": api_key,
        "x-chain": birdeye_chain,
        "Accept": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        # Fetch token metadata for name and symbol
        metadata_url = f"{base_url}/defi/v3/token/meta-data/single"
        params = {"address": token_address}

        async with session.get(metadata_url, headers=headers, params=params, timeout=30) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"BirdEye meta-data API error: {response.status} - {error_text}")

            metadata_response = await response.json()

        # Fetch basic market data
        market_url = f"{base_url}/defi/v3/token/market-data"

        async with session.get(market_url, headers=headers, params=params, timeout=30) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"BirdEye market-data API error: {response.status} - {error_text}")

            market_data = await response.json()

        # Fetch trade data for volume and price changes
        trade_url = f"{base_url}/defi/v3/token/trade-data/single"

        async with session.get(trade_url, headers=headers, params=params, timeout=30) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"BirdEye trade-data API error: {response.status} - {error_text}")

            trade_data = await response.json()

        # Fetch 5-minute OHLCV data
        ohlcv_url = f"{base_url}/defi/ohlcv"
        ohlcv_params = {
            "address": token_address,
            "type": "5m",  # 5-minute timeframe
            "limit": 1  # Get latest candle only
        }

        ohlcv_data = None
        try:
            async with session.get(ohlcv_url, headers=headers, params=ohlcv_params, timeout=30) as response:
                if response.status == 200:
                    ohlcv_response = await response.json()
                    if ohlcv_response.get("success") and ohlcv_response.get("data"):
                        items = ohlcv_response["data"].get("items", [])
                        if items:
                            # Get the latest 5-minute candle
                            latest_candle = items[0]
                            ohlcv_data = {
                                "timestamp": latest_candle.get("timestamp"),
                                "open": safe_float(latest_candle.get("open")),
                                "high": safe_float(latest_candle.get("high")),
                                "low": safe_float(latest_candle.get("low")),
                                "close": safe_float(latest_candle.get("close")),
                                "volume": safe_float(latest_candle.get("volume"))
                            }
                else:
                    print(f"⚠️  OHLCV data not available: {response.status}")
        except Exception as e:
            print(f"⚠️  Failed to fetch OHLCV data: {str(e)}")

    # Extract data from responses
    metadata_info = metadata_response.get("data", {})
    token_info = market_data.get("data", {})
    trade_info = trade_data.get("data", {})

    # Extract market metrics
    price_usd = safe_float(token_info.get("price"))
    liquidity_usd = safe_float(token_info.get("liquidity"))
    market_cap_usd = safe_float(token_info.get("market_cap"))
    fdv_usd = safe_float(token_info.get("total_supply", 0)) * price_usd if price_usd > 0 else market_cap_usd or 0

    # Get volume from trade data
    volume_24h_usd = safe_float(trade_info.get("volume_24h_usd", 0))

    # Get price changes from trade data
    price_change_24h = safe_float(trade_info.get("price_change_24h_percent", 0))
    price_change_1h = safe_float(trade_info.get("price_change_1h_percent", 0))

    # Extract token metadata from metadata endpoint
    token_symbol = metadata_info.get("symbol", "Unknown")
    token_name = metadata_info.get("name", token_symbol)

    print(f"✅ Successfully fetched BirdEye data for {token_symbol} (${price_usd:.6f})")
    print(f"   Volume 24h: ${volume_24h_usd:,.2f}")
    print(f"   Liquidity: ${liquidity_usd:,.2f}")
    if ohlcv_data:
        print(f"   OHLCV (5m): O:{ohlcv_data['open']:.6f} H:{ohlcv_data['high']:.6f} L:{ohlcv_data['low']:.6f} C:{ohlcv_data['close']:.6f}")

    return TokenMarketData(
        price_usd=price_usd,
        fdv_usd=fdv_usd,
        market_cap_usd=market_cap_usd,
        volume_24h_usd=volume_24h_usd,
        liquidity_usd=liquidity_usd,
        price_change_24h_percent=price_change_24h,
        price_change_1h_percent=price_change_1h,
        token_symbol=token_symbol,
        token_name=token_name,
        ohlcv_5m=ohlcv_data
    )


async def fetch_moralis_holder_data(
    chain: str, token_address: str
) -> Optional[TokenHolderData]:
    """Fetch holder statistics from Moralis API (returns None for Shibarium)"""

    # Skip Moralis for Shibarium as specified
    if chain.lower() == "shibarium":
        print("⚠️  Skipping holder data for Shibarium (not supported by Moralis)")
        return None

    api_key = os.getenv("MORALIS_API_KEY")
    if not api_key:
        print("⚠️  MORALIS_API_KEY not set - skipping holder data")
        return None

    # Map chains to Moralis chain names
    chain_map = {
        "ethereum": "eth",
        "base": "base",
        "bnb": "bsc",
        "bsc": "bsc",  # Support both "bnb" and "bsc" as input
    }

    # For Solana, use Solana gateway endpoint
    if chain.lower() == "solana":
        url = f"https://solana-gateway.moralis.io/token/mainnet/holders/{token_address}"
        headers = {
            "X-API-Key": api_key,
            "Accept": "application/json",
        }
        params = None
    else:
        # EVM chains
        chain_name = chain_map.get(chain.lower())
        if not chain_name:
            print(f"⚠️  Chain {chain} not supported by Moralis")
            return None

        url = f"https://deep-index.moralis.io/api/v2.2/erc20/{token_address}/holders"
        headers = {
            "X-API-Key": api_key,
            "Accept": "application/json",
        }
        params = {"chain": chain_name}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=30,
            ) as response:
                if response.status != 200:
                    print(f"⚠️  Moralis API error: {response.status}")
                    return None

                data = await response.json()

                # Handle null response
                if data is None:
                    print(f"⚠️  No holder data available for this token")
                    return None

                # Extract metrics from new Moralis API response structure
                total_holders = data.get("totalHolders", 0)

                # Get top 10 concentration from holderSupply.top10.supplyPercent
                holder_supply = data.get("holderSupply", {})
                top10_info = holder_supply.get("top10", {})
                top10_concentration = top10_info.get("supplyPercent", 0)

                # Get 24h holder change
                holder_change = data.get("holderChange", {})
                holder_change_24h = holder_change.get("24h", {}).get("change", None)

                return TokenHolderData(
                    total_holders=total_holders,
                    top10_concentration=top10_concentration,
                    holder_change_24h=holder_change_24h,
                    chain=chain,
                )

        except Exception as e:
            print(f"❌ Failed to fetch holder data from Moralis: {str(e)}")
            return None


async def fetch_token_creation_info(token_address: str) -> Optional[CreationInfo]:
    """Fetch token creation information from BirdEye API"""

    api_key = os.getenv("BIRDEYE_API_KEY")
    if not api_key:
        raise Exception("BIRDEYE_API_KEY not found in environment variables")

    base_url = "https://public-api.birdeye.so"
    headers = {
        "X-API-KEY": api_key,
        "x-chain": "solana",  # Bundler is Solana-only
        "Accept": "application/json"
    }

    url = f"{base_url}/defi/token_creation_info"
    params = {"address": token_address}

    print(f"🦅 Fetching creation info for {token_address}")

    async with aiohttp.ClientSession() as session:
        # Add rate limiting sleep
        await asyncio.sleep(0.2)  # 5 RPS limit

        async with session.get(url, headers=headers, params=params, timeout=30) as response:
            if response.status != 200:
                error_text = await response.text()
                print(f"⚠️  Failed to fetch creation info: {response.status} - {error_text}")
                return None

            data = await response.json()
            creation_data = data.get("data")

            if not creation_data:
                print(f"⚠️  No creation info available for {token_address}")
                return None

            # Extract creation info
            block_unix_time = creation_data.get("blockUnixTime")
            block_human_time = creation_data.get("blockHumanTime")
            tx_hash = creation_data.get("txHash", "")

            if not block_unix_time:
                print(f"⚠️  Missing timestamp in creation info")
                return None

            return CreationInfo(
                created_at=block_human_time or iso_timestamp(block_unix_time),
                creation_tx=tx_hash,
                block_unix_time=block_unix_time
            )


async def fetch_moralis_transactions(
    token_address: str,
    from_date: int,
    limit: int = 500
) -> List[Dict[str, Any]]:
    """
    Fetch transaction history from Moralis API in ascending order.

    Args:
        token_address: Solana token address
        from_date: Unix timestamp to start fetching from
        limit: Maximum number of transactions to fetch

    Returns:
        List of transaction dictionaries in BirdEye-compatible format
    """
    api_key = os.getenv("MORALIS_API_KEY")
    if not api_key:
        print("⚠️  MORALIS_API_KEY not set - skipping transaction data")
        return []

    print(f"🐺 Fetching transactions from Moralis for {token_address}")
    print(f"   From date: {datetime.fromtimestamp(from_date)}")
    print(f"   Target limit: {limit} transactions")

    base_url = "https://solana-gateway.moralis.io/token/mainnet"
    headers = {
        "Accept": "application/json",
        "X-API-Key": api_key
    }

    transactions = []
    cursor = None

    async with aiohttp.ClientSession() as session:
        while len(transactions) < limit:
            # Calculate optimal page size (don't fetch more than needed)
            remaining = limit - len(transactions)
            page_size = min(25, remaining)  # Moralis max is 25 per page
            url = f"{base_url}/{token_address}/swaps"
            params = {
                "fromDate": from_date,
                "order": "ASC",
                "transactionTypes": "buy",
                "limit": page_size
            }

            if cursor:
                params["cursor"] = cursor

            # Add rate limiting
            await asyncio.sleep(0.2)

            try:
                async with session.get(url, headers=headers, params=params, timeout=30) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"⚠️  Moralis API error: {response.status} - {error_text}")
                        break

                    data = await response.json()
                    result = data.get("result", [])

                    if not result:
                        break

                    # Convert Moralis format to BirdEye-compatible format
                    converted_txs = []
                    for tx in result:
                        try:
                            # Convert timestamp to unix
                            block_time_str = tx.get("blockTimestamp", "")
                            block_unix_time = int(datetime.fromisoformat(block_time_str.replace('Z', '+00:00')).timestamp())

                            # Extract bought token info
                            bought = tx.get("bought", {})
                            sold = tx.get("sold", {})

                            converted_tx = {
                                "tx_type": "buy",
                                "tx_hash": tx.get("transactionHash", ""),
                                "block_unix_time": block_unix_time,
                                "block_number": tx.get("blockNumber", 0),
                                "owner": tx.get("walletAddress", ""),
                                "to": {
                                    "address": bought.get("address", ""),
                                    "symbol": bought.get("symbol", ""),
                                    "ui_amount": float(bought.get("amount", 0))
                                },
                                "from": {
                                    "address": sold.get("address", ""),
                                    "symbol": sold.get("symbol", ""),
                                    "ui_amount": float(sold.get("amount", 0))
                                }
                            }
                            converted_txs.append(converted_tx)
                        except Exception as e:
                            print(f"⚠️  Error converting transaction: {str(e)}")
                            continue

                    transactions.extend(converted_txs)
                    print(f"   Page fetched: {len(converted_txs)} transactions (total: {len(transactions)})")

                    # Check if there are more pages
                    cursor = data.get("cursor")
                    if not cursor or len(result) < page_size:
                        print(f"   Pagination complete: {'no more cursor' if not cursor else 'partial page received'}")
                        break

            except Exception as e:
                print(f"❌ Error fetching from Moralis: {str(e)}")
                break

    print(f"✅ Fetched {len(transactions)} buy transactions from Moralis")
    return transactions[:limit]


async def fetch_token_transactions(
    token_address: str,
    limit: int = 500,
    max_pages: int = 5,
    after_time: Optional[int] = None,
    before_time: Optional[int] = None,
    sort_ascending: bool = False
) -> List[Dict[str, Any]]:
    """
    Fetch transaction history from BirdEye API.

    Args:
        token_address: Solana token address
        limit: Maximum number of transactions to fetch
        max_pages: Maximum number of pages to fetch (100 per page)
        after_time: Unix timestamp - fetch transactions after this time
        before_time: Unix timestamp - fetch transactions before this time
    """

    api_key = os.getenv("BIRDEYE_API_KEY")
    if not api_key:
        raise Exception("BIRDEYE_API_KEY not found in environment variables")

    base_url = "https://public-api.birdeye.so"
    headers = {
        "X-API-KEY": api_key,
        "x-chain": "solana",  # Bundler is Solana-only
        "Accept": "application/json"
    }

    print(f"🦅 Fetching transaction history for {token_address}")
    if after_time or before_time:
        time_msg = []
        if after_time:
            time_msg.append(f"after {datetime.fromtimestamp(after_time).strftime('%Y-%m-%d %H:%M:%S')}")
        if before_time:
            time_msg.append(f"before {datetime.fromtimestamp(before_time).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Time window: {' and '.join(time_msg)}")

    transactions = []

    async with aiohttp.ClientSession() as session:
        for page in range(max_pages):
            offset = page * 100
            url = f"{base_url}/defi/v3/token/txs"
            params = {
                "address": token_address,
                "offset": offset,
                "limit": 100,
                "sort_by": "block_unix_time",
                "sort_type": "asc" if sort_ascending else "desc",
                "tx_type": "buy",  # Only fetch buy transactions for bundle detection
                "ui_amount_mode": "scaled"
            }

            # Add time window parameters if provided
            if after_time:
                params["after_time"] = after_time
            if before_time:
                params["before_time"] = before_time

            # Add rate limiting sleep
            await asyncio.sleep(0.2)  # 5 RPS limit

            async with session.get(url, headers=headers, params=params, timeout=30) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"⚠️  Failed to fetch transactions page {page}: {response.status} - {error_text}")
                    break

                data = await response.json()
                items = data.get("data", {}).get("items", [])

                if not items:
                    break

                # Filter for buy transactions only
                buy_txs = []
                for item in items:
                    tx_type = item.get("tx_type") or item.get("side", "")
                    if tx_type == "buy":
                        buy_txs.append(item)

                transactions.extend(buy_txs)

                # Stop if we have enough or this page wasn't full
                if len(transactions) >= limit or len(items) < 100:
                    break

    # Limit to requested amount
    transactions = transactions[:limit]
    print(f"✅ Fetched {len(transactions)} buy transactions")

    return transactions


async def fetch_bundler_analysis(token_address: str) -> Optional[BundlerAnalysis]:
    """
    Orchestrate complete bundler analysis for a Solana token.

    Args:
        token_address: Solana token contract address

    Returns:
        BundlerAnalysis object or None if analysis fails
    """
    print(f"🔍 Starting bundler analysis for {token_address}")

    try:
        # Step 1: Fetch token creation info
        creation_info = await fetch_token_creation_info(token_address)
        if not creation_info:
            print(f"⚠️  Cannot perform bundler analysis: creation info unavailable")
            return BundlerAnalysis(
                bundled_detected=False,
                bundle_cluster_count=0,
                bundle_clusters=[],
                creation_info=None,
                risk_metrics=None,
                total_bundled_tokens=None,
                present_impact_analysis=None,
                price_action_analysis=None,
                meta={
                    "error": "Creation info unavailable",
                    "analysis_time": iso_timestamp(int(time.time())),
                    "source": "BirdEye API"
                }
            )

        print(f"✅ Token created at: {creation_info.created_at}")

        # Step 2: Fetch the first 300 buy transactions from launch onward
        # Use creation time as starting point, sort ascending to get earliest transactions first
        launch_time = creation_info.block_unix_time
        search_start_time = launch_time - 1  # Start 1 second before to catch exact launch

        print(f"🔍 Fetching first 300 buy transactions from launch time: {datetime.fromtimestamp(launch_time)}")

        # Use Moralis for Solana transactions (supports ASC order)
        transactions = await fetch_moralis_transactions(
            token_address,
            from_date=search_start_time,
            limit=300
        )
        if not transactions:
            print(f"⚠️  No transaction history available for bundler analysis")
            return BundlerAnalysis(
                bundled_detected=False,
                bundle_cluster_count=0,
                bundle_clusters=[],
                creation_info=creation_info,
                risk_metrics=None,
                total_bundled_tokens=None,
                present_impact_analysis=None,
                price_action_analysis=None,
                meta={
                    "error": "No transaction history available",
                    "analysis_time": iso_timestamp(int(time.time())),
                    "source": "Moralis API"
                }
            )

        print(f"✅ Analyzing {len(transactions)} transactions for bundles")

        # Step 3: Detect bundles
        bundled_detected, bundle_clusters, total_bundled_tokens = detect_bundles(
            transactions,
            creation_info.block_unix_time
        )

        # Calculate risk metrics, present impact analysis, and price action analysis
        risk_metrics = None
        present_impact = None
        price_action = None

        if bundled_detected:
            print(f"📊 Calculating risk metrics for {len(bundle_clusters)} bundle clusters...")

            # Calculate comprehensive risk metrics
            risk_metrics = calculate_bundle_risk_metrics(
                bundle_clusters,
                transactions,
                len(transactions)
            )

            # Analyze present-day impact of bundled wallets
            present_impact = await analyze_present_impact(
                bundle_clusters,
                transactions,
                token_address,
                "solana"
            )

            # Analyze price action for sell-off patterns (3-day window from first transaction)
            if transactions:
                first_tx_time = transactions[0].get("block_unix_time", 0)
                if first_tx_time > 0:
                    # Get time range: from first transaction to 3 days later
                    ohlcv_start = first_tx_time
                    ohlcv_end = first_tx_time + (3 * 24 * 60 * 60)  # 3 days later

                    # Fetch OHLCV data
                    ohlcv_data = await fetch_ohlcv_data(
                        token_address,
                        ohlcv_start,
                        ohlcv_end,
                        timeframe="1D"  # Daily candles for 3-day window
                    )

                    if ohlcv_data:
                        price_action = analyze_price_action_selloff(ohlcv_data, first_tx_time)

            print(f"🎯 Risk Assessment:")
            print(f"   Bundle Intensity: {risk_metrics.bundle_intensity_score}/100")
            print(f"   Coordination Level: {risk_metrics.coordination_sophistication}")
            print(f"   Early Trading Dominance: {risk_metrics.early_trading_dominance}% of first 300 txs")
            if present_impact:
                print(f"   Present Impact: {present_impact.get('current_impact_risk', 'UNKNOWN')}")
                print(f"   Analysis Method: {present_impact.get('analysis_method', 'UNKNOWN')}")
            if price_action:
                print(f"   Price Action: {price_action.get('selloff_severity', 'UNKNOWN')} sell-off detected")
                print(f"   Risk Mitigation: {price_action.get('risk_mitigation_factor', 'NONE')}")
        else:
            print(f"📊 No bundles detected - calculating baseline risk metrics...")
            risk_metrics = calculate_bundle_risk_metrics([], transactions, len(transactions))

        # Step 4: Create analysis result
        analysis = BundlerAnalysis(
            bundled_detected=bundled_detected,
            bundle_cluster_count=len(bundle_clusters),
            bundle_clusters=bundle_clusters,
            creation_info=creation_info,
            risk_metrics=risk_metrics,
            total_bundled_tokens=total_bundled_tokens,
            present_impact_analysis=present_impact,
            price_action_analysis=price_action,
            meta={
                "transactions_analyzed": len(transactions),
                "analysis_time": iso_timestamp(int(time.time())),
                "source": "Moralis API for transactions, BirdEye for creation info and OHLCV",
                "first_n_transactions": 300,
                "ohlcv_window_days": 3
            }
        )

        if bundled_detected:
            total_bundled_txs = sum(cluster.cluster_size for cluster in bundle_clusters)
            print(f"🚨 Bundle detected! {len(bundle_clusters)} clusters with {total_bundled_txs} total transactions")
            for i, cluster in enumerate(bundle_clusters):
                print(f"   Cluster {i+1}: {cluster.cluster_size} txs, {cluster.unique_wallets} wallets, score: {cluster.score}")
        else:
            print(f"✅ No bundles detected - launch appears organic")

        # Calculate percentage of bundled transactions for user display
        if bundled_detected:
            # Count unique transactions that fall within any bundle cluster (avoid double counting)
            bundled_tx_indices = set()
            for cluster in bundle_clusters:
                cluster_start = cluster.first_unix
                cluster_end = cluster_start + cluster.window_seconds

                for idx, tx in enumerate(transactions):
                    tx_time = tx.get("block_unix_time") or tx.get("blockUnixTime", 0)
                    if cluster_start <= tx_time <= cluster_end:
                        bundled_tx_indices.add(idx)

            unique_bundled_count = len(bundled_tx_indices)
            bundled_percentage = (unique_bundled_count / len(transactions) * 100) if transactions else 0
            analysis.meta["bundled_transaction_percentage"] = round(bundled_percentage, 1)
        else:
            analysis.meta["bundled_transaction_percentage"] = 0

        return analysis

    except Exception as e:
        print(f"❌ Bundler analysis failed: {str(e)}")
        return BundlerAnalysis(
            bundled_detected=False,
            bundle_cluster_count=0,
            bundle_clusters=[],
            creation_info=None,
            risk_metrics=None,
            total_bundled_tokens=None,
            present_impact_analysis=None,
            price_action_analysis=None,
            meta={
                "error": str(e),
                "analysis_time": iso_timestamp(int(time.time())),
                "source": "Moralis/BirdEye API"
            }
        )


async def fetch_all_token_data(token_address: str, chain: str) -> Dict[str, Any]:
    """
    Fetch all token data from external APIs before agency initialization
    Now using BirdEye instead of GeckoTerminal

    Args:
        token_address: Token contract address
        chain: Blockchain name (solana, ethereum, base, bnb, shibarium)

    Returns:
        Dictionary containing market data, holder data, and token metadata
    """

    print(f"🔍 Fetching market and holder data for {token_address} on {chain}")

    # Create tasks for parallel fetching of independent data sources
    tasks = []

    # Task 1: Market data from BirdEye (required)
    async def fetch_market():
        try:
            return await fetch_birdeye_market_data(chain, token_address)
        except Exception as e:
            print(f"❌ Failed to fetch market data: {str(e)}")
            # Try to provide helpful error message
            if "BIRDEYE_API_KEY" in str(e):
                raise Exception("BIRDEYE_API_KEY not set. Please add it to your .env file")
            else:
                raise Exception(f"Cannot proceed without market data: {str(e)}")

    # Task 2: Holder data from Moralis (optional)
    async def fetch_holders():
        try:
            holder_data = await fetch_moralis_holder_data(chain, token_address)
            if holder_data:
                print(
                    f"✅ Fetched holder data: {holder_data.total_holders} holders, "
                    f"{holder_data.top10_concentration:.1f}% concentration"
                )
            return holder_data
        except Exception as e:
            print(f"⚠️  Holder data unavailable: {str(e)}")
            return None

    # Execute market and holder fetching in parallel
    print(f"⚡ Fetching market and holder data in parallel...")
    market_data, holder_data = await asyncio.gather(
        fetch_market(),
        fetch_holders()
    )

    # Task 3: Bundler analysis for Solana tokens only
    async def fetch_bundler():
        if chain.lower() != "solana":
            print(f"⚠️  Skipping bundler analysis for {chain} (Solana only feature)")
            return None
        try:
            print(f"🔍 Running bundler analysis for Solana token...")
            bundler_analysis = await fetch_bundler_analysis(token_address)
            if bundler_analysis:
                bundler_data = {
                    "bundled_detected": bundler_analysis.bundled_detected,
                    "bundle_cluster_count": bundler_analysis.bundle_cluster_count,
                    "total_bundled_tokens": bundler_analysis.total_bundled_tokens,
                    "bundled_transaction_percentage": bundler_analysis.meta.get("bundled_transaction_percentage", 0),
                    "risk_metrics": (
                        {
                            "bundle_intensity_score": bundler_analysis.risk_metrics.bundle_intensity_score,
                            "wallet_concentration_risk": bundler_analysis.risk_metrics.wallet_concentration_risk,
                            "bundle_timing_consistency": bundler_analysis.risk_metrics.bundle_timing_consistency,
                            "early_trading_dominance": bundler_analysis.risk_metrics.early_trading_dominance,
                            "coordination_sophistication": bundler_analysis.risk_metrics.coordination_sophistication
                        }
                        if bundler_analysis.risk_metrics
                        else None
                    ),
                    "present_impact_analysis": bundler_analysis.present_impact_analysis,
                    "price_action_analysis": bundler_analysis.price_action_analysis,
                    "bundle_clusters": [
                        {
                            "cluster_size": cluster.cluster_size,
                            "window_seconds": cluster.window_seconds,
                            "unique_wallets": cluster.unique_wallets,
                            "wallet_diversity_ratio": cluster.wallet_diversity_ratio,
                            "score": cluster.score,
                            "sample_txs": cluster.sample_txs,
                            "first_unix": cluster.first_unix
                        }
                        for cluster in bundler_analysis.bundle_clusters
                    ],
                    "creation_info": (
                        {
                            "created_at": bundler_analysis.creation_info.created_at,
                            "creation_tx": bundler_analysis.creation_info.creation_tx,
                            "block_unix_time": bundler_analysis.creation_info.block_unix_time
                        }
                        if bundler_analysis.creation_info
                        else None
                    ),
                    "meta": bundler_analysis.meta
                }

                # Log bundler results
                if bundler_analysis.bundled_detected:
                    print(f"🚨 Bundler analysis complete: {bundler_analysis.bundle_cluster_count} bundles detected")
                else:
                    print(f"✅ Bundler analysis complete: No bundles detected")
                return bundler_data
        except Exception as e:
            print(f"⚠️  Bundler analysis failed: {str(e)}")
            return {
                "bundled_detected": False,
                "bundle_cluster_count": 0,
                "total_bundled_tokens": None,
                "bundled_transaction_percentage": 0,
                "risk_metrics": None,
                "present_impact_analysis": None,
                "price_action_analysis": None,
                "bundle_clusters": [],
                "creation_info": None,
                "meta": {"error": str(e)}
            }

    # Task 4: 24h market health analysis for all chains
    async def fetch_market_health():
        try:
            print(f"📊 Running 24h market health analysis...")
            market_health_analysis = await analyze_24h_market_health(token_address, chain)
            if market_health_analysis and market_health_analysis.get("market_health_available", False):
                market_health_data = {
                "market_health_available": True,
                "market_health": market_health_analysis.get("market_health"),
                "sentiment_factors": market_health_analysis.get("sentiment_factors"),
                "buy_pressure_pct": market_health_analysis.get("buy_pressure_pct"),
                "sell_pressure_pct": market_health_analysis.get("sell_pressure_pct"),
                "pressure_dominance": market_health_analysis.get("pressure_dominance"),
                "avg_volume_per_period_usd": market_health_analysis.get("avg_volume_per_period_usd"),
                "high_24h": market_health_analysis.get("h24_high"),
                "low_24h": market_health_analysis.get("h24_low"),
                "current_price": market_health_analysis.get("current_price"),
                "price_change_24h_pct": market_health_analysis.get("price_change_24h_pct"),
                "total_volume_24h_usd": market_health_analysis.get("total_volume_24h_usd"),
                "volume_change_pct": market_health_analysis.get("volume_change_pct"),
                "avg_volatility_pct": market_health_analysis.get("avg_volatility_pct"),
                "data_points": market_health_analysis.get("data_points"),
                "analysis_note": market_health_analysis.get("analysis_note")
                }
                print(f"📈 Market health analysis complete: {market_health_data.get('market_health', 'N/A')}")
                return market_health_data
            else:
                # OHLCV data not available or insufficient
                market_health_data = {
                    "market_health_available": False,
                    "analysis_note": market_health_analysis.get("analysis_note", "Insufficient data"),
                    "data_points": market_health_analysis.get("data_points", 0)
                }
                print(f"⚠️  24h market health analysis unavailable: {market_health_data.get('analysis_note')}")
                return market_health_data
        except Exception as e:
            print(f"⚠️  24h market health analysis failed: {str(e)}")
            return {
                "market_health_available": False,
                "error": str(e),
                "analysis_note": f"Analysis failed: {str(e)}"
            }

    # Task 4: Token safety analysis
    async def fetch_safety():
        try:
            from token_safety import analyze_token_safety
            print(f"🔒 Fetching token safety analysis...")
            safety_result = await analyze_token_safety(token_address, chain)
            if safety_result.get("success"):
                print(f"✅ Token safety analysis completed")
                return safety_result.get("analysis")
            else:
                print(f"⚠️  Token safety analysis failed: {safety_result.get('error')}")
                return None
        except Exception as e:
            print(f"⚠️  Token safety analysis failed: {str(e)}")
            return None

    # Execute bundler, market health, and safety analysis in parallel
    print(f"⚡ Running bundler, market health, and safety analysis in parallel...")
    bundler_data, market_health_data, safety_data = await asyncio.gather(
        fetch_bundler(),
        fetch_market_health(),
        fetch_safety()
    )

    return {
        "token_address": token_address,
        "chain": chain,
        "token_symbol": market_data.token_symbol,
        "token_name": market_data.token_name,
        "market_data": {
            "price_usd": market_data.price_usd,
            "fdv_usd": market_data.fdv_usd,
            "market_cap_usd": market_data.market_cap_usd,
            "volume_24h_usd": market_data.volume_24h_usd,
            "liquidity_usd": market_data.liquidity_usd,
            "price_change_24h_percent": market_data.price_change_24h_percent,
            "price_change_1h_percent": market_data.price_change_1h_percent,
            "ohlcv_5m": market_data.ohlcv_5m,
        },
        "holder_data": (
            {
                "total_holders": holder_data.total_holders,
                "top10_concentration": holder_data.top10_concentration,
                "holder_change_24h": holder_data.holder_change_24h,
            }
            if holder_data
            else None
        ),
        "bundler_analysis": bundler_data,
        "market_health_24h": market_health_data,
        "safety_analysis": safety_data,
    }