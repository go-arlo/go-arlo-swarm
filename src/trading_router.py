"""
Trading API Router
Provides endpoints for trading analysis and execution using structured data
"""

import asyncio
import json
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from enum import Enum
import os

from rejection_tracker import get_rejection_tracker

# Cache for rejections endpoint (30 second TTL)
_rejections_cache = {}
_rejections_cache_ttl = 30

from auth import verify_api_key

# Import our trading analyzer
from trading_analyzer import (
    TradingAnalyzer,
    TradingCriteria,
    TradingRecommendation,
    get_conservative_criteria,
    get_moderate_criteria,
    get_aggressive_criteria,
    get_strict_default_criteria,
    RiskLevel,
    ConcentrationLevel,
    MarketPressure
)

from trading_system import ComprehensiveTradingSystem
from token_list_fetcher import TokenListPresets

# Import trading tools from consolidated module
try:
    from trading_tools import (
        GetJupiterQuote,
        CalculatePositionSize,
        ExecuteJupiterSwap,
        WalletManager
    )
except ImportError as e:
    print(f"Warning: Could not import trading tools: {e}")
    GetJupiterQuote = None
    CalculatePositionSize = None
    ExecuteJupiterSwap = None
    WalletManager = None

# Create router
router = APIRouter(prefix="/trading", tags=["Trading"])

# Global trading analyzer with default criteria
current_analyzer = TradingAnalyzer(get_moderate_criteria())

trading_system_state: Dict[str, Any] = {
    "system": None,
    "task": None,
    "running": False,
    "started_at": None,
    "config": None
}


class AnalysisRequest(BaseModel):
    """Request model for structured data analysis"""
    token_address: str = Field(..., description="Token contract address")
    chain: str = Field(default="solana", description="Blockchain (solana, ethereum, etc.)")
    # Optional structured data fields - if not provided, will be fetched
    market_data: Optional[Dict[str, Any]] = Field(None, description="Market data from BirdEye")
    holder_data: Optional[Dict[str, Any]] = Field(None, description="Holder data from Moralis")
    bundler_analysis: Optional[Dict[str, Any]] = Field(None, description="Bundler analysis")
    market_health_24h: Optional[Dict[str, Any]] = Field(None, description="24h market health")
    sentiment_data: Optional[Dict[str, Any]] = Field(None, description="Sentiment/TweetScout data")
    safety_analysis: Optional[Dict[str, Any]] = Field(None, description="Token safety analysis")


class CriteriaUpdateRequest(BaseModel):
    """Request model for updating trading criteria"""
    max_overall_risk: Optional[RiskLevel] = None
    max_concentration: Optional[ConcentrationLevel] = None
    max_bundler_risk: Optional[RiskLevel] = None
    required_pressure: Optional[list[MarketPressure]] = None
    min_volume_change_percent: Optional[float] = None
    allow_negative_social: Optional[bool] = None
    min_liquidity_usd: Optional[float] = None
    min_holders: Optional[int] = None


class QuoteRequest(BaseModel):
    """Request model for getting Jupiter quote"""
    input_mint: str = Field(..., description="Input token mint address")
    output_mint: str = Field(..., description="Output token mint address")
    amount: str = Field(..., description="Amount to swap (in smallest unit)")
    slippage_bps: int = Field(default=100, description="Slippage in basis points")


class SwapRequest(BaseModel):
    """Request model for executing swap"""
    input_mint: str = Field(..., description="Input token mint address")
    output_mint: str = Field(..., description="Output token mint address")
    amount: str = Field(..., description="Amount to swap (in smallest unit)")
    slippage_bps: int = Field(default=100, description="Slippage in basis points")


class AutoSwapRequest(BaseModel):
    """Request model for auto-executing swap based on structured data"""
    token_address: str = Field(..., description="Token contract address to buy")
    chain: str = Field(default="solana", description="Blockchain")
    input_mint: str = Field(
        default="So11111111111111111111111111111111111111112",
        description="Input token mint (default: SOL)"
    )
    portfolio_percent: Optional[float] = Field(
        10.0,
        description="Percentage of input token balance to use"
    )
    max_amount: Optional[float] = Field(
        None,
        description="Maximum amount to spend in SOL"
    )
    # Optional pre-fetched structured data
    market_data: Optional[Dict[str, Any]] = Field(None, description="Market data")
    holder_data: Optional[Dict[str, Any]] = Field(None, description="Holder data")
    bundler_analysis: Optional[Dict[str, Any]] = Field(None, description="Bundler analysis")
    market_health_24h: Optional[Dict[str, Any]] = Field(None, description="24h market health")
    sentiment_data: Optional[Dict[str, Any]] = Field(None, description="Sentiment data")
    safety_analysis: Optional[Dict[str, Any]] = Field(None, description="Token safety")


@router.get("/")
async def trading_root():
    """Trading API root endpoint"""
    return {
        "service": "Trading API",
        "version": "2.1.0",
        "endpoints": {
            "analysis": [
                "/trading/analyze",
                "/trading/auto-execute",
                "/trading/criteria",
                "/trading/criteria/presets/{preset}",
                "/trading/presets"
            ],
            "execution": [
                "/trading/quote",
                "/trading/execute"
            ],
            "system_management": [
                "/trading/system/start",
                "/trading/system/stop",
                "/trading/system/status",
                "/trading/system/filter-presets",
                "/trading/system/risk-profiles"
            ],
            "monitoring": [
                "/trading/health",
                "/trading/rejections",
                "/trading/rejections/stats"
            ]
        },
        "description": "Analyze token data, execute trades, and manage automated trading system"
    }


@router.post("/analyze", response_model=TradingRecommendation)
async def analyze_token(request: AnalysisRequest):
    """
    Analyze token and get trading recommendation

    Uses structured data directly from data sources.
    If structured data fields are not provided, they will be fetched automatically.
    """
    try:
        from data_fetchers import fetch_all_token_data

        # Build structured data dict
        structured_data = {
            "market_data": request.market_data,
            "holder_data": request.holder_data,
            "bundler_analysis": request.bundler_analysis,
            "market_health_24h": request.market_health_24h,
            "sentiment_data": request.sentiment_data,
            "safety_analysis": request.safety_analysis,
        }

        # If key data is missing, fetch it
        if not any([request.safety_analysis, request.holder_data, request.market_health_24h]):
            fetched_data = await fetch_all_token_data(request.token_address, request.chain)
            # Merge fetched data with any provided data (provided takes precedence)
            for key in structured_data:
                if structured_data[key] is None:
                    structured_data[key] = fetched_data.get(key)

        # Create fresh analyzer and analyze structured data
        analyzer = TradingAnalyzer(current_analyzer.criteria)
        recommendation = analyzer.analyze_structured_data(structured_data)
        return recommendation
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/criteria")
async def get_current_criteria():
    """
    Get current trading criteria settings

    Shows the current thresholds and requirements for trading decisions.
    """
    return {
        "current_criteria": current_analyzer.criteria.dict(),
        "description": "Current trading decision criteria"
    }


@router.put("/criteria")
async def update_criteria(request: CriteriaUpdateRequest):
    """
    Update trading criteria settings

    Modify the thresholds and requirements for trading decisions.
    """
    global current_analyzer

    try:
        # Get current criteria as dict
        current_dict = current_analyzer.criteria.dict()

        # Update with provided values
        update_dict = request.dict(exclude_unset=True)
        current_dict.update(update_dict)

        # Create new criteria and analyzer
        new_criteria = TradingCriteria(**current_dict)
        current_analyzer = TradingAnalyzer(new_criteria)

        return {
            "success": True,
            "message": "Trading criteria updated",
            "new_criteria": new_criteria.dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/criteria/presets/{preset}")
async def set_criteria_preset(preset: str):
    """
    Set trading criteria to a preset configuration

    Available presets: conservative, moderate, aggressive
    """
    global current_analyzer

    preset_functions = {
        "conservative": get_conservative_criteria,
        "moderate": get_moderate_criteria,
        "aggressive": get_aggressive_criteria
    }

    if preset not in preset_functions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid preset. Available: {list(preset_functions.keys())}"
        )

    try:
        new_criteria = preset_functions[preset]()
        current_analyzer = TradingAnalyzer(new_criteria)

        return {
            "success": True,
            "message": f"Trading criteria set to {preset} preset",
            "criteria": new_criteria.dict()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quote")
async def get_trading_quote(request: QuoteRequest):
    """
    Get Jupiter swap quote for trading analysis

    Use this to check prices and slippage before executing trades.
    """
    if GetJupiterQuote is None:
        raise HTTPException(
            status_code=503,
            detail="Jupiter quote tool not available"
        )

    try:
        quote_tool = GetJupiterQuote(
            input_mint=request.input_mint,
            output_mint=request.output_mint,
            amount=request.amount,
            slippage_bps=request.slippage_bps
        )

        result = quote_tool.run()

        # Parse the result if it's a string
        if isinstance(result, str):
            return {
                "success": True,
                "quote_result": result,
                "input_mint": request.input_mint,
                "output_mint": request.output_mint,
                "amount": request.amount
            }
        else:
            return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute")
async def execute_swap(request: SwapRequest, api_key: str = Depends(verify_api_key)):
    """
    Execute Jupiter swap (requires API key)

    WARNING: This will execute an actual trade with real funds.
    """
    if ExecuteJupiterSwap is None:
        raise HTTPException(
            status_code=503,
            detail="Jupiter swap tool not available"
        )

    try:
        swap_tool = ExecuteJupiterSwap(
            input_mint=request.input_mint,
            output_mint=request.output_mint,
            amount=request.amount,
            slippage_bps=request.slippage_bps
        )

        result = swap_tool.run()

        return {
            "success": True,
            "execution_result": result,
            "trade_details": {
                "input_mint": request.input_mint,
                "output_mint": request.output_mint,
                "amount": request.amount,
                "slippage_bps": request.slippage_bps
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto-execute")
async def auto_execute_trade(request: AutoSwapRequest, api_key: str = Depends(verify_api_key)):
    """
    Analyze token and auto-execute trade if criteria are met (requires API key)

    Uses structured data directly.
    WARNING: This will execute actual trades with real funds if conditions are met.
    """
    try:
        from data_fetchers import fetch_all_token_data

        # Build structured data dict
        structured_data = {
            "market_data": request.market_data,
            "holder_data": request.holder_data,
            "bundler_analysis": request.bundler_analysis,
            "market_health_24h": request.market_health_24h,
            "sentiment_data": request.sentiment_data,
            "safety_analysis": request.safety_analysis,
        }

        # If key data is missing, fetch it
        if not any([request.safety_analysis, request.holder_data, request.market_health_24h]):
            fetched_data = await fetch_all_token_data(request.token_address, request.chain)
            for key in structured_data:
                if structured_data[key] is None:
                    structured_data[key] = fetched_data.get(key)

        # Analyze using structured data
        analyzer = TradingAnalyzer(current_analyzer.criteria)
        recommendation = analyzer.analyze_structured_data(structured_data)

        if recommendation.action != "BUY":
            return {
                "action_taken": "NONE",
                "reason": f"Analysis result was {recommendation.action}, not BUY",
                "recommendation": recommendation.dict()
            }

        # Check if DELEGATED_WALLET_ADDRESS is configured
        delegated_wallet = os.getenv("DELEGATED_WALLET_ADDRESS")
        if not delegated_wallet:
            return {
                "action_taken": "FAILED",
                "reason": "No DELEGATED_WALLET_ADDRESS configured",
                "recommendation": recommendation.dict()
            }

        # Calculate actual amount based on portfolio percentage
        if request.portfolio_percent and WalletManager:
            try:
                wallet_manager = WalletManager(
                    delegated_wallet_address=delegated_wallet,
                    turnkey_organization_id=os.getenv("TURNKEY_ORGANIZATION_ID"),
                    solana_rpc_url=os.getenv(
                        "SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com"
                    )
                )

                sol_balance = wallet_manager.get_sol_balance()
                if not sol_balance:
                    return {
                        "action_taken": "FAILED",
                        "reason": "Could not fetch wallet balance",
                        "recommendation": recommendation.dict()
                    }

                # Calculate swap amount (leave 0.01 SOL for fees)
                available_balance = max(0, sol_balance - 0.01)
                swap_amount = (request.portfolio_percent / 100.0) * available_balance

                # Apply max_amount limit
                max_amount = request.max_amount or float(os.getenv("MAX_AMOUNT", "0.1"))
                swap_amount = min(swap_amount, max_amount)

                if swap_amount <= 0:
                    return {
                        "action_taken": "FAILED",
                        "reason": f"Insufficient balance. Current: {sol_balance:.6f} SOL",
                        "recommendation": recommendation.dict()
                    }

                # Execute swap
                if ExecuteJupiterSwap:
                    swap_tool = ExecuteJupiterSwap(
                        input_mint=request.input_mint,
                        output_mint=request.token_address,
                        amount=str(int(swap_amount * 1e9)),
                        slippage_bps=100
                    )
                    execution_result = swap_tool.run()

                    return {
                        "action_taken": "EXECUTED",
                        "recommendation": recommendation.dict(),
                        "execution_result": execution_result,
                        "swap_details": {
                            "token_address": request.token_address,
                            "sol_balance": sol_balance,
                            "percentage_used": request.portfolio_percent,
                            "amount_sol": swap_amount
                        }
                    }
            except Exception as e:
                return {
                    "action_taken": "FAILED",
                    "reason": f"Execution error: {str(e)}",
                    "recommendation": recommendation.dict()
                }

        return {
            "action_taken": "ANALYSIS_ONLY",
            "reason": "Auto-execution tools not available",
            "recommendation": recommendation.dict()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presets")
async def get_available_presets():
    """
    Get available criteria presets with descriptions

    Shows the different risk profiles available for trading.
    """
    return {
        "presets": {
            "conservative": {
                "description": "Safest settings - Low risk, high requirements",
                "criteria": get_conservative_criteria().dict()
            },
            "moderate": {
                "description": "Balanced settings - Default configuration",
                "criteria": get_moderate_criteria().dict()
            },
            "aggressive": {
                "description": "Riskier settings - Lower requirements, higher risk tolerance",
                "criteria": get_aggressive_criteria().dict()
            }
        }
    }


@router.get("/health")
async def trading_health():
    """
    Check trading system health and tool availability

    Useful for monitoring which trading features are available.
    """
    tools_status = {
        "jupiter_quote": GetJupiterQuote is not None,
        "position_calculator": CalculatePositionSize is not None,
        "jupiter_swap": ExecuteJupiterSwap is not None
    }

    all_available = all(tools_status.values())

    return {
        "status": "healthy" if all_available else "partial",
        "analyzer_ready": True,
        "current_preset": "moderate",
        "tools_available": tools_status,
        "message": "All systems operational" if all_available else "Some trading tools unavailable"
    }


def _format_rejection_reason(reason: str) -> str:
    """
    Format rejection reason for display.
    Parses JSON reason data and returns comma-separated list of failed criteria.
    """
    try:
        data = json.loads(reason)
        if isinstance(data, dict) and "failed" in data:
            failed = data["failed"]
            # Format criterion names: token_safety -> Token Safety
            formatted = [c.replace("_", " ").title() for c in failed]
            return ", ".join(formatted) if formatted else "No criteria failed"
        return reason
    except (json.JSONDecodeError, TypeError):
        return reason  # Return as-is if not JSON


@router.get("/rejections")
async def get_rejected_tokens(
    limit: int = Query(default=50, ge=1, le=500, description="Max tokens to return"),
    chain: Optional[str] = Query(default=None, description="Filter by chain (e.g., solana)")
):
    """
    Get rejected tokens sorted by timestamp (latest first)

    Returns tokens that were analyzed and rejected by the trading system.
    Each rejection includes formatted_reason showing which criteria failed.
    Results are cached for 30 seconds to reduce database load.
    """
    try:
        # Check cache first
        cache_key = f"{chain}:{limit}"
        now = datetime.now(timezone.utc)
        if cache_key in _rejections_cache:
            cached = _rejections_cache[cache_key]
            cache_age = (now - cached["timestamp"]).total_seconds()
            if cache_age < _rejections_cache_ttl:
                return cached["response"]

        tracker = get_rejection_tracker()
        tokens = tracker.get_rejected_tokens(chain=chain)

        # Sort by timestamp descending (latest first)
        tokens.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

        # Apply limit
        tokens = tokens[:limit]

        # Format each rejection with comma-separated failed criteria
        for token in tokens:
            raw_reason = token.get("reason", "")
            token["failed_criteria"] = _format_rejection_reason(raw_reason)
            # Remove raw JSON reason from response
            del token["reason"]

        response = {
            "success": True,
            "count": len(tokens),
            "limit": limit,
            "chain_filter": chain,
            "rejections": tokens
        }

        # Store in cache
        _rejections_cache[cache_key] = {
            "timestamp": now,
            "response": response
        }

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rejections/stats")
async def get_rejection_stats():
    """
    Get rejection statistics

    Returns summary stats about rejected tokens by chain and reason.
    """
    try:
        tracker = get_rejection_tracker()
        stats = tracker.get_stats()

        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# TRADING SYSTEM MANAGEMENT ENDPOINTS
# =============================================================================

class RiskProfile(str, Enum):
    """Available risk profiles"""
    STRICT = "strict"
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class FilterPreset(str, Enum):
    """Available token filter presets"""
    OPTIMIZED_DEFAULT = "optimized_default"
    DAILY_DRIVER = "daily_driver"
    HIGH_MOMENTUM = "high_momentum"
    VOLUME_LIQUIDITY_BALANCED = "volume_liquidity_balanced"
    HIGH_LIQUIDITY_TRENDING = "high_liquidity_trending"
    NEW_LISTINGS = "new_listings"
    RECENT_LISTINGS_72H = "recent_listings_72h"


class ProfitTier(BaseModel):
    """Profit tier configuration"""
    profit_percent: float = Field(..., description="Profit % to trigger sell")
    sell_percent: float = Field(..., description="% of holdings to sell")


class TradingSystemStartRequest(BaseModel):
    """Request model for starting the trading system"""
    live_trading: bool = Field(
        default=False,
        description="Enable live trading (real money). False = dry run mode"
    )
    cycles: int = Field(
        default=1,
        ge=0,
        le=999,
        description="Number of cycles to run (0 for continuous/infinite)"
    )
    interval_minutes: int = Field(
        default=3,
        ge=1,
        le=60,
        description="Minutes between trading cycles"
    )
    risk_profile: RiskProfile = Field(
        default=RiskProfile.STRICT,
        description="Risk profile for trading decisions"
    )
    enable_auto_sell: bool = Field(
        default=False,
        description="Enable automatic selling based on PnL"
    )
    sell_check_interval: int = Field(
        default=30,
        ge=10,
        le=300,
        description="Seconds between sell checks when auto-sell is enabled"
    )
    loss_threshold: float = Field(
        default=-10.0,
        ge=-50.0,
        le=0.0,
        description="Stop loss percentage (e.g., -10 for -10%)"
    )
    profit_tiers: Optional[List[ProfitTier]] = Field(
        default=None,
        description="Custom profit-taking tiers. Default: 30:30, 100:30, 200:25, 900:15"
    )
    max_trade_amount: Optional[float] = Field(
        default=None,
        ge=0.001,
        le=10.0,
        description="Maximum SOL per trade (overrides MAX_AMOUNT env var)"
    )
    filter_preset: FilterPreset = Field(
        default=FilterPreset.OPTIMIZED_DEFAULT,
        description="Token filter preset for discovery"
    )


class TradingSystemResponse(BaseModel):
    """Response model for trading system operations"""
    success: bool
    message: str
    status: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


async def run_trading_system(
    system: ComprehensiveTradingSystem,
    cycles: int,
    interval_minutes: int
):
    """Background task to run the trading system"""
    try:
        trading_system_state["running"] = True
        await system.run(cycles=cycles, interval_minutes=interval_minutes)
    except asyncio.CancelledError:
        print("🛑 Trading system task cancelled")
    except Exception as e:
        print(f"❌ Trading system error: {e}")
    finally:
        trading_system_state["running"] = False
        trading_system_state["system"] = None
        trading_system_state["task"] = None


@router.post("/system/start", response_model=TradingSystemResponse)
async def start_trading_system(
    request: TradingSystemStartRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """
    Start the automated trading system (requires API key)

    Starts token discovery, analysis, and trading based on configured parameters.
    Use dry_run mode (live_trading=false) to test without real trades.
    """
    global trading_system_state

    # Check if already running
    if trading_system_state["running"]:
        raise HTTPException(
            status_code=409,
            detail="Trading system is already running. Stop it first."
        )

    try:
        # Convert profit tiers if provided
        profit_tiers = None
        if request.profit_tiers:
            profit_tiers = [
                (tier.profit_percent, tier.sell_percent)
                for tier in request.profit_tiers
            ]

        # Create trading system instance
        system = ComprehensiveTradingSystem(
            dry_run=not request.live_trading,
            risk_profile=request.risk_profile.value,
            enable_auto_sell=request.enable_auto_sell,
            sell_check_interval=request.sell_check_interval,
            loss_threshold=request.loss_threshold,
            profit_tiers=profit_tiers,
            max_trade_amount=request.max_trade_amount
        )

        # Store configuration
        config = {
            "live_trading": request.live_trading,
            "cycles": request.cycles,
            "interval_minutes": request.interval_minutes,
            "risk_profile": request.risk_profile.value,
            "enable_auto_sell": request.enable_auto_sell,
            "sell_check_interval": request.sell_check_interval,
            "loss_threshold": request.loss_threshold,
            "profit_tiers": request.profit_tiers,
            "max_trade_amount": request.max_trade_amount,
            "filter_preset": request.filter_preset.value
        }

        # Start the system in background
        task = asyncio.create_task(
            run_trading_system(system, request.cycles, request.interval_minutes)
        )

        # Update global state
        trading_system_state["system"] = system
        trading_system_state["task"] = task
        trading_system_state["running"] = True
        trading_system_state["started_at"] = datetime.now().isoformat()
        trading_system_state["config"] = config

        mode = "🔥 LIVE" if request.live_trading else "🎭 DRY RUN"

        return TradingSystemResponse(
            success=True,
            message=f"Trading system started in {mode} mode",
            status="running",
            config=config
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system/stop", response_model=TradingSystemResponse)
async def stop_trading_system(api_key: str = Depends(verify_api_key)):
    """
    Stop the automated trading system (requires API key)

    Gracefully stops the trading system if it's running.
    """
    global trading_system_state

    if not trading_system_state["running"]:
        return TradingSystemResponse(
            success=True,
            message="Trading system is not running",
            status="stopped"
        )

    try:
        # Save config before cancellation (task's finally block clears state)
        config = trading_system_state.get("config")
        system = trading_system_state.get("system")
        task = trading_system_state.get("task")

        # Stop the system
        if system:
            system.running = False
            print("🛑 Set system.running = False")

        # Cancel the task
        if task:
            print("🛑 Cancelling trading system task...")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                print("🛑 Task cancelled successfully")

        # Reset state (may already be cleared by task's finally block)
        trading_system_state["system"] = None
        trading_system_state["task"] = None
        trading_system_state["running"] = False
        trading_system_state["started_at"] = None
        trading_system_state["config"] = None

        return TradingSystemResponse(
            success=True,
            message="Trading system stopped",
            status="stopped",
            config=config
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/status")
async def get_trading_system_status():
    """
    Get current trading system status

    Returns whether the system is running and its current configuration.
    """
    if not trading_system_state["running"]:
        return {
            "status": "stopped",
            "running": False,
            "started_at": None,
            "config": None
        }

    # Get rejection stats for summary
    tracker = get_rejection_tracker()
    stats = tracker.get_stats()

    return {
        "status": "running",
        "running": True,
        "started_at": trading_system_state["started_at"],
        "config": trading_system_state["config"],
        "rejection_stats": stats
    }


@router.get("/system/filter-presets")
async def get_filter_presets():
    """
    Get available token filter presets

    Shows all available presets for token discovery with their configurations.
    """
    return {
        "presets": {
            "optimized_default": {
                "description": "Optimized default (30min-72h age, $50k liq, $75k 1h vol)",
                "params": TokenListPresets.optimized_default().dict()
            },
            "daily_driver": {
                "description": "Daily driver for consistent opportunities",
                "params": TokenListPresets.daily_driver().dict()
            },
            "high_momentum": {
                "description": "High momentum for aggressive plays",
                "params": TokenListPresets.high_momentum().dict()
            },
            "volume_liquidity_balanced": {
                "description": "Volume/liquidity balanced (1.5x-6x ratio)",
                "params": TokenListPresets.volume_liquidity_balanced().dict()
            },
            "high_liquidity_trending": {
                "description": "High liquidity with volume increase",
                "params": TokenListPresets.high_liquidity_trending().dict()
            },
            "new_listings": {
                "description": "Recently listed (last 24 hours)",
                "params": TokenListPresets.new_listings().dict()
            },
            "recent_listings_72h": {
                "description": "Recently listed within 72 hours",
                "params": TokenListPresets.recent_listings_72h().dict()
            }
        },
        "default": "optimized_default"
    }


@router.get("/system/risk-profiles")
async def get_risk_profiles():
    """
    Get available risk profiles with their criteria

    Shows all available risk profiles and their trading criteria configurations.
    """
    return {
        "profiles": {
            "strict": {
                "description": "Strictest settings - ALL criteria must pass (recommended)",
                "criteria": get_strict_default_criteria().dict()
            },
            "conservative": {
                "description": "Conservative - Very safe, only Positive sentiment + Unlikely scam",
                "criteria": get_conservative_criteria().dict()
            },
            "moderate": {
                "description": "Moderate - Balanced risk tolerance",
                "criteria": get_moderate_criteria().dict()
            },
            "aggressive": {
                "description": "Aggressive - Higher risk, all sentiments allowed",
                "criteria": get_aggressive_criteria().dict()
            }
        },
        "default": "strict"
    }
