"""
Token List API Router
Provides FastAPI routes for token list fetching and job management
Separated for better abstraction and integration with main.py
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Depends
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

from auth import verify_api_key

from token_list_fetcher import (
    TokenListParams,
    TokenListResponse,
    fetch_token_list,
    fetch_all_pages,
    TokenListPresets,
    SortBy,
    SortType,
    UIAmountMode
)
from token_list_scheduler import (
    get_scheduler,
    JobConfig,
    JobStatus
)

# Create router instead of app
router = APIRouter(prefix="/token-list", tags=["Token List"])


class JobCreateRequest(BaseModel):
    """Request model for creating a scheduled job"""
    job_id: str = Field(..., description="Unique job identifier")
    name: str = Field(..., description="Job name")
    description: Optional[str] = Field(None, description="Job description")
    params: Optional[TokenListParams] = Field(None, description="Query parameters")
    preset_name: Optional[str] = Field(
        None,
        description="Use a preset configuration instead of custom params"
    )
    chain: str = Field(default="solana", description="Blockchain")
    interval_minutes: int = Field(
        default=5,
        ge=1,
        le=1440,
        description="Interval between runs (1-1440 minutes)"
    )
    max_pages: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Max pages to fetch per run"
    )
    apply_ratio_filter: bool = Field(
        default=False,
        description="Apply volume/liquidity ratio filter (auto for volume_liquidity_balanced)"
    )
    min_ratio: float = Field(
        default=1.5,
        description="Minimum volume/liquidity ratio"
    )
    max_ratio: float = Field(
        default=6.0,
        description="Maximum volume/liquidity ratio"
    )
    auto_start: bool = Field(
        default=True,
        description="Start job immediately after creation"
    )


class JobResponse(BaseModel):
    """Response model for job operations"""
    success: bool
    message: str
    job_id: Optional[str] = None
    status: Optional[Dict[str, Any]] = None


@router.get("/")
async def token_list_root():
    """Token List API root endpoint"""
    return {
        "service": "Token List API",
        "version": "1.0.0",
        "endpoints": [
            "/token-list/fetch",
            "/token-list/presets",
            "/token-list/jobs/create",
            "/token-list/jobs/list",
            "/token-list/jobs/{job_id}/status",
            "/token-list/jobs/{job_id}/pause",
            "/token-list/jobs/{job_id}/resume",
            "/token-list/jobs/{job_id}/delete",
            "/token-list/jobs/{job_id}/run"
        ]
    }


@router.post("/fetch", response_model=TokenListResponse)
async def fetch_tokens(
    params: TokenListParams,
    chain: str = Query(default="solana", description="Blockchain to query"),
    fetch_all: bool = Query(
        default=False,
        description="Fetch all available pages (up to 10)"
    ),
    max_pages: int = Query(
        default=10,
        ge=1,
        le=10,
        description="Max pages to fetch if fetch_all=true"
    ),
    apply_ratio_filter: bool = Query(
        default=False,
        description="Apply volume/liquidity ratio filter"
    ),
    min_ratio: float = Query(
        default=1.5,
        description="Minimum volume/liquidity ratio"
    ),
    max_ratio: float = Query(
        default=6.0,
        description="Maximum volume/liquidity ratio"
    )
):
    """
    Manually fetch token list with specified parameters

    This endpoint allows for one-time token list fetching with custom parameters.
    """
    try:
        if fetch_all:
            response = await fetch_all_pages(
                params, chain, max_pages,
                apply_ratio_filter, min_ratio, max_ratio
            )
        else:
            response = await fetch_token_list(
                params, chain,
                apply_ratio_filter, min_ratio, max_ratio
            )

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presets")
async def get_presets():
    """
    Get available parameter presets

    Returns preset configurations for common token filtering scenarios.
    """
    return {
        "presets": {
            "high_liquidity_trending": {
                "description": "Tokens with high liquidity and recent volume increase",
                "params": TokenListPresets.high_liquidity_trending().dict()
            },
            "new_listings": {
                "description": "Recently listed tokens (last 24 hours)",
                "params": TokenListPresets.new_listings().dict()
            },
            "recent_listings_72h": {
                "description": "Recently listed tokens within 72 hours",
                "params": TokenListPresets.recent_listings_72h().dict()
            },
            "high_volume_movers": {
                "description": "High volume tokens with significant price movement",
                "params": TokenListPresets.high_volume_movers().dict()
            },
            "established_tokens": {
                "description": "Well-established tokens with good metrics",
                "params": TokenListPresets.established_tokens().dict()
            },
            "momentum_plays": {
                "description": "High momentum tokens with strong volume and liquidity",
                "params": TokenListPresets.momentum_plays().dict()
            },
            "daily_driver": {
                "description": "Daily driver settings for consistent trading opportunities",
                "params": TokenListPresets.daily_driver().dict()
            },
            "high_momentum": {
                "description": "High momentum settings for aggressive plays",
                "params": TokenListPresets.high_momentum().dict()
            },
            "volume_liquidity_balanced": {
                "description": "Volume/Liquidity balanced for optimal trading (30m-72h age)",
                "params": TokenListPresets.volume_liquidity_balanced().dict()
            },
            "optimized_default": {
                "description": "New optimized default filter (5-filter limit compliant)",
                "params": TokenListPresets.optimized_default().dict()
            }
        }
    }


@router.post("/fetch-preset", response_model=TokenListResponse)
async def fetch_with_preset(
    preset_name: str = Query(
        default="optimized_default",
        description="Preset name: high_liquidity_trending, new_listings, "
                    "recent_listings_72h, high_volume_movers, established_tokens, "
                    "momentum_plays, daily_driver, high_momentum, volume_liquidity_balanced, optimized_default"
    ),
    chain: str = Query(default="solana", description="Blockchain to query")
):
    """
    Fetch tokens using a preset configuration

    Quick way to fetch tokens with predefined parameter sets.
    """
    presets = {
        "high_liquidity_trending": TokenListPresets.high_liquidity_trending(),
        "new_listings": TokenListPresets.new_listings(),
        "recent_listings_72h": TokenListPresets.recent_listings_72h(),
        "high_volume_movers": TokenListPresets.high_volume_movers(),
        "established_tokens": TokenListPresets.established_tokens(),
        "momentum_plays": TokenListPresets.momentum_plays(),
        "daily_driver": TokenListPresets.daily_driver(),
        "high_momentum": TokenListPresets.high_momentum(),
        "volume_liquidity_balanced": TokenListPresets.volume_liquidity_balanced(),
        "optimized_default": TokenListPresets.optimized_default()
    }

    if preset_name not in presets:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid preset. Available: {list(presets.keys())}"
        )

    try:
        # Apply ratio filtering automatically for volume_liquidity_balanced and optimized_default presets
        apply_ratio_filter = preset_name in ["volume_liquidity_balanced", "optimized_default"]

        # Use different ratio ranges for different presets
        if preset_name == "optimized_default":
            min_ratio, max_ratio = 1.5, 5.0
        else:
            min_ratio, max_ratio = 1.5, 6.0

        response = await fetch_token_list(
            presets[preset_name], chain,
            apply_ratio_filter=apply_ratio_filter,
            min_ratio=min_ratio,
            max_ratio=max_ratio
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/create", response_model=JobResponse)
async def create_job(request: JobCreateRequest, api_key: str = Depends(verify_api_key)):
    """
    Create a new scheduled token fetching job

    Creates a job that will fetch tokens at specified intervals.
    Can use either custom params or a preset configuration.
    """
    scheduler = get_scheduler()

    try:
        # Get params from preset or use custom params
        if request.preset_name:
            presets = {
                "high_liquidity_trending": TokenListPresets.high_liquidity_trending(),
                "new_listings": TokenListPresets.new_listings(),
                "recent_listings_72h": TokenListPresets.recent_listings_72h(),
                "high_volume_movers": TokenListPresets.high_volume_movers(),
                "established_tokens": TokenListPresets.established_tokens(),
                "momentum_plays": TokenListPresets.momentum_plays(),
                "daily_driver": TokenListPresets.daily_driver(),
                "high_momentum": TokenListPresets.high_momentum(),
                "volume_liquidity_balanced": TokenListPresets.volume_liquidity_balanced(),
                "optimized_default": TokenListPresets.optimized_default()
            }
            if request.preset_name not in presets:
                raise ValueError(f"Invalid preset: {request.preset_name}")
            params = presets[request.preset_name]
        elif request.params:
            params = request.params
        else:
            raise ValueError("Either params or preset_name must be provided")

        job = scheduler.add_job(
            job_id=request.job_id,
            name=request.name,
            params=params,
            interval_minutes=request.interval_minutes,
            chain=request.chain,
            max_pages=request.max_pages,
            description=request.description,
            apply_ratio_filter=request.apply_ratio_filter,
            min_ratio=request.min_ratio,
            max_ratio=request.max_ratio,
            preset_name=request.preset_name
        )

        return JobResponse(
            success=True,
            message=f"Job '{request.name}' created successfully",
            job_id=request.job_id,
            status=scheduler.get_job_status(request.job_id)
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/list")
async def list_jobs():
    """
    List all scheduled jobs

    Returns information about all configured token fetching jobs.
    """
    scheduler = get_scheduler()
    return {
        "jobs": scheduler.list_jobs(),
        "total": len(scheduler.list_jobs())
    }


@router.get("/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    """
    Get status of a specific job

    Returns detailed status information for the specified job.
    """
    scheduler = get_scheduler()
    status = scheduler.get_job_status(job_id)

    if status is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return status


@router.post("/jobs/{job_id}/pause", response_model=JobResponse)
async def pause_job(job_id: str, api_key: str = Depends(verify_api_key)):
    """
    Pause a scheduled job

    Temporarily stops the job from running at its scheduled intervals.
    """
    scheduler = get_scheduler()

    if scheduler.pause_job(job_id):
        return JobResponse(
            success=True,
            message=f"Job {job_id} paused",
            job_id=job_id,
            status=scheduler.get_job_status(job_id)
        )
    else:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


@router.post("/jobs/{job_id}/resume", response_model=JobResponse)
async def resume_job(job_id: str, api_key: str = Depends(verify_api_key)):
    """
    Resume a paused job

    Resumes a job that was previously paused.
    """
    scheduler = get_scheduler()

    if scheduler.resume_job(job_id):
        return JobResponse(
            success=True,
            message=f"Job {job_id} resumed",
            job_id=job_id,
            status=scheduler.get_job_status(job_id)
        )
    else:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


@router.delete("/jobs/{job_id}", response_model=JobResponse)
async def delete_job(job_id: str, api_key: str = Depends(verify_api_key)):
    """
    Delete a scheduled job

    Permanently removes the job from the scheduler.
    """
    scheduler = get_scheduler()

    if scheduler.remove_job(job_id):
        return JobResponse(
            success=True,
            message=f"Job {job_id} deleted",
            job_id=job_id
        )
    else:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


@router.post("/jobs/{job_id}/run", response_model=JobResponse)
async def run_job_once(
    job_id: str,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    """
    Run a job immediately (one-time)

    Executes the job once outside of its regular schedule.
    """
    scheduler = get_scheduler()

    if job_id not in scheduler.jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Run in background to avoid blocking
    background_tasks.add_task(scheduler.run_job_once, job_id)

    return JobResponse(
        success=True,
        message=f"Job {job_id} execution started",
        job_id=job_id
    )


# Helper endpoint for parameter documentation
@router.get("/params/info")
async def get_param_info():
    """
    Get information about available query parameters

    Returns detailed information about all available filtering parameters.
    """
    return {
        "sort_fields": [e.value for e in SortBy],
        "sort_types": [e.value for e in SortType],
        "ui_amount_modes": [e.value for e in UIAmountMode],
        "parameters": {
            "sort_by": {
                "type": "string",
                "required": True,
                "default": "liquidity",
                "options": [e.value for e in SortBy]
            },
            "sort_type": {
                "type": "string",
                "required": True,
                "default": "desc",
                "options": [e.value for e in SortType]
            },
            "min_liquidity": {
                "type": "number",
                "required": False,
                "description": "Minimum liquidity in USD"
            },
            "max_liquidity": {
                "type": "number",
                "required": False,
                "description": "Maximum liquidity in USD"
            },
            "min_market_cap": {
                "type": "number",
                "required": False,
                "description": "Minimum market cap in USD"
            },
            "max_market_cap": {
                "type": "number",
                "required": False,
                "description": "Maximum market cap in USD"
            },
            "min_recent_listing_hours_ago": {
                "type": "number",
                "required": False,
                "description": "Tokens listed within last N hours"
            },
            "max_recent_listing_hours_ago": {
                "type": "number",
                "required": False,
                "description": "Tokens listed more than N hours ago"
            },
            "min_last_trade_hours_ago": {
                "type": "number",
                "required": False,
                "description": "Last traded within N hours"
            },
            "max_last_trade_hours_ago": {
                "type": "number",
                "required": False,
                "description": "Last traded more than N hours ago"
            },
            "min_holder": {
                "type": "integer",
                "required": False,
                "description": "Minimum number of holders"
            },
            "min_volume_24h_usd": {
                "type": "number",
                "required": False,
                "description": "Minimum 24h volume in USD"
            },
            "min_volume_24h_change_percent": {
                "type": "number",
                "required": False,
                "description": "Minimum 24h volume change percentage"
            },
            "min_price_change_24h_percent": {
                "type": "number",
                "required": False,
                "description": "Minimum 24h price change percentage"
            },
            "offset": {
                "type": "integer",
                "required": False,
                "default": 0,
                "description": "Pagination offset (0-10000)"
            },
            "limit": {
                "type": "integer",
                "required": False,
                "default": 20,
                "description": "Results per page (1-20)"
            }
        }
    }