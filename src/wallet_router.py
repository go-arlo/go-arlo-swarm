"""
Agency Wallet API Router
Simplified API for tracking the agency's wallet and making sell decisions
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from pydantic import BaseModel, Field

from auth import verify_api_key
from wallet_fetcher import (
    WalletPnLResponse,
    WalletPnLSummary,
    fetch_wallet_pnl,
    fetch_wallet_pnl_summary,
    WalletPnLTracker,
    fetch_recent_trades_from_pnl
)
from auto_sell_command import EnhancedProgressiveSellStrategy

# Create router with prefix
router = APIRouter(prefix="/wallet", tags=["Agency Wallet"])

# Single agency tracker (simplified - only track one wallet)
agency_pnl_tracker: WalletPnLTracker = None
agency_sell_strategy: EnhancedProgressiveSellStrategy = None


class AgencySetupRequest(BaseModel):
    """Setup the agency wallet for PnL tracking"""
    wallet_address: str = Field(..., description="Agency wallet address")
    chain: str = Field(default="solana", description="Blockchain")
    loss_threshold: float = Field(default=-10.0, description="Hard stop loss percentage")
    trailing_stop_activation: float = Field(default=60.0, description="Profit % to activate trailing stop")
    trailing_stop_distance: float = Field(default=12.0, description="Trailing stop distance %")
    profit_tiers: list = Field(
        default=None,
        description="List of [profit_percent, sell_percent] pairs. "
                   "Default: [[30, 30], [100, 30], [200, 25], [900, 15]]"
    )


class RecentTradesRequest(BaseModel):
    """Request for recent trades endpoint"""
    wallet_address: str = Field(..., description="Wallet address to fetch trades for")
    chain: str = Field(default="solana", description="Blockchain (solana, ethereum, etc.)")
    limit: int = Field(default=20, ge=1, le=100, description="Number of tokens to return")


@router.get("/")
async def wallet_root():
    """Agency Wallet API root endpoint"""
    return {
        "service": "Agency Wallet API",
        "version": "1.0.0",
        "endpoints": [
            "/wallet/setup",
            "/wallet/pnl",
            "/wallet/pnl-summary",
            "/wallet/sell-signals",
            "/wallet/recent-trades (POST)"
        ],
        "purpose": "Track agency wallet PnL and provide progressive sell recommendations"
    }


@router.post("/setup")
async def setup_agency_wallet(
    request: AgencySetupRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Setup the agency wallet for PnL tracking with progressive sell strategy

    This is the main setup endpoint to start tracking the agency's wallet PnL.
    """
    global agency_pnl_tracker, agency_sell_strategy

    try:
        # Create the PnL tracker
        agency_pnl_tracker = WalletPnLTracker(
            wallet_address=request.wallet_address,
            chain=request.chain
        )

        # Create enhanced progressive sell strategy with trailing stop
        agency_sell_strategy = EnhancedProgressiveSellStrategy(
            loss_threshold=request.loss_threshold,
            profit_tiers=request.profit_tiers,
            trailing_stop_activation=request.trailing_stop_activation,
            trailing_stop_distance=request.trailing_stop_distance
        )

        # Get initial state
        initial_pnl = await agency_pnl_tracker.update_pnl()

        return {
            "success": True,
            "message": "Agency wallet PnL tracking setup complete",
            "wallet_address": request.wallet_address,
            "total_value": initial_pnl["total_current_value"],
            "token_count": initial_pnl["token_count"],
            "strategy": {
                "loss_threshold": request.loss_threshold,
                "trailing_stop_activation": request.trailing_stop_activation,
                "trailing_stop_distance": request.trailing_stop_distance,
                "profit_tiers": request.profit_tiers or [
                    [30, 30],   # 1.3x
                    [100, 30],  # 2x
                    [200, 25],  # 3x
                    [900, 15]   # 10x
                ]
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pnl")
async def get_agency_pnl():
    """
    Get current agency wallet PnL status with unrealized gains/losses

    Quick check of the current wallet PnL state.
    """
    global agency_pnl_tracker

    if agency_pnl_tracker is None:
        raise HTTPException(
            status_code=404,
            detail="Agency wallet not setup. Use /wallet/setup first."
        )

    try:
        pnl_summary = await agency_pnl_tracker.update_pnl()

        return {
            "wallet_address": agency_pnl_tracker.wallet_address,
            "total_current_value": pnl_summary["total_current_value"],
            "total_invested": pnl_summary["total_invested"],
            "total_unrealized_usd": pnl_summary["total_unrealized_usd"],
            "total_unrealized_percent": pnl_summary["total_unrealized_percent"],
            "token_count": pnl_summary["token_count"],
            "timestamp": pnl_summary["timestamp"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pnl-summary")
async def get_wallet_pnl_summary(wallet_address: str = None, chain: str = "solana"):
    """
    Get wallet PnL summary with realized profit percentage and win rate

    Args:
        wallet_address: Wallet address (optional, uses DELEGATED_WALLET_ADDRESS if not provided)
        chain: Blockchain (default: "solana")

    Returns:
        Wallet PnL summary with key trading performance metrics
    """
    try:
        summary = await fetch_wallet_pnl_summary(
            wallet_address=wallet_address,
            chain=chain
        )

        return {
            "success": summary.success,
            "wallet_address": summary.wallet_address,
            "realized_profit_percent": summary.realized_profit_percent,
            "win_rate": summary.win_rate,
            "total_realized_profit": summary.total_realized_profit,
            "total_trades": summary.total_trades,
            "winning_trades": summary.winning_trades,
            "losing_trades": summary.losing_trades,
            "chain": summary.chain,
            "timestamp": summary.fetch_timestamp
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sell-signals")
async def get_sell_signals():
    """
    Get progressive sell recommendations based on unrealized PnL percentages

    This is the main endpoint for making sell decisions based on PnL.
    """
    global agency_pnl_tracker, agency_sell_strategy

    if agency_pnl_tracker is None or agency_sell_strategy is None:
        raise HTTPException(
            status_code=404,
            detail="Agency wallet not setup. Use /wallet/setup first."
        )

    try:
        pnl_summary = await agency_pnl_tracker.update_pnl()

        # Generate progressive sell recommendations
        sell_signals = agency_sell_strategy.generate_sell_signals(pnl_summary["tokens"])

        # Return focused sell signal information
        return {
            "wallet_address": agency_pnl_tracker.wallet_address,
            "total_current_value": pnl_summary["total_current_value"],
            "total_unrealized_percent": pnl_summary["total_unrealized_percent"],
            "sell_recommendations": sell_signals,
            "timestamp": pnl_summary["timestamp"],
            "message": f"Found {len(sell_signals)} progressive sell signals"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recent-trades")
async def get_recent_trades(request: RecentTradesRequest):
    """
    Get recent buy and sell trades from wallet PnL data.

    Tokens with total_buy >= 1 are included in recent_buys.
    Tokens with total_sell >= 1 are included in recent_sells.
    SOL and USDC are excluded.

    Returns:
        PnL data along with recent_buys and recent_sells arrays
    """
    try:
        trades = await fetch_recent_trades_from_pnl(
            wallet_address=request.wallet_address,
            chain=request.chain,
            limit=request.limit
        )

        return {
            "success": trades.success,
            "wallet_address": trades.wallet_address,
            "total_current_value": trades.total_current_value,
            "total_invested": trades.total_invested,
            "total_unrealized_usd": trades.total_unrealized_usd,
            "total_unrealized_percent": trades.total_unrealized_percent,
            "tokens": [t.model_dump() for t in trades.tokens],
            "token_count": trades.token_count,
            "recent_buys": [{"address": t.address, "symbol": t.symbol} for t in trades.recent_buys],
            "recent_sells": [{"address": t.address, "symbol": t.symbol} for t in trades.recent_sells],
            "timestamp": trades.fetch_timestamp,
            "chain": trades.chain
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))