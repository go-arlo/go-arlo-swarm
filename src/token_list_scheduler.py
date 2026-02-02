"""
Job scheduler for periodic token list fetching
Manages background jobs that fetch token lists at regular intervals
"""

import asyncio
import json
import os
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.job import Job
from pydantic import BaseModel, Field
from enum import Enum

from token_list_fetcher import (
    TokenListParams,
    TokenListResponse,
    fetch_token_list,
    fetch_all_pages,
    TokenListPresets
)


class JobStatus(str, Enum):
    """Status of a scheduled job"""
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class JobConfig(BaseModel):
    """Configuration for a token list fetch job"""
    job_id: str
    name: str
    description: Optional[str] = None
    params: TokenListParams
    chain: str = "solana"
    interval_minutes: int = Field(default=3, ge=1, le=1440)
    max_pages: int = Field(default=1, ge=1, le=10)
    apply_ratio_filter: bool = Field(
        default=False,
        description="Apply volume/liquidity ratio filtering"
    )
    min_ratio: float = Field(default=1.5, description="Min volume/liquidity ratio")
    max_ratio: float = Field(default=6.0, description="Max volume/liquidity ratio")
    preset_name: Optional[str] = Field(
        None,
        description="Name of preset used (for auto ratio filtering)"
    )
    callback: Optional[str] = Field(
        None,
        description="Optional callback function name to process results"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_run: Optional[datetime] = None
    last_status: JobStatus = JobStatus.ACTIVE
    last_error: Optional[str] = None


class TokenListJob(BaseModel):
    """Represents a scheduled token list fetch job"""
    config: JobConfig
    apscheduler_job_id: Optional[str] = None
    results_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="History of recent fetch results"
    )
    run_count: int = 0
    error_count: int = 0


class TokenListScheduler:
    """
    Manages scheduled jobs for fetching token lists
    """

    def __init__(
        self,
        results_dir: str = "./token_list_results",
        max_history: int = 10
    ):
        """
        Initialize the scheduler

        Args:
            results_dir: Directory to store fetch results
            max_history: Maximum number of results to keep in history
        """
        self.scheduler = AsyncIOScheduler()
        self.jobs: Dict[str, TokenListJob] = {}
        self.results_dir = results_dir
        self.max_history = max_history
        self.callbacks: Dict[str, Callable] = {}
        self._running = False

        os.makedirs(results_dir, exist_ok=True)

    def register_callback(
        self,
        name: str,
        callback: Callable[[TokenListResponse], None]
    ):
        """
        Register a callback function to process fetch results

        Args:
            name: Name to reference the callback
            callback: Function that takes TokenListResponse as input
        """
        self.callbacks[name] = callback
        print(f"✅ Registered callback: {name}")

    async def _execute_job(self, job_id: str):
        """
        Execute a scheduled job

        Args:
            job_id: ID of the job to execute
        """
        if job_id not in self.jobs:
            print(f"❌ Job {job_id} not found")
            return

        job = self.jobs[job_id]
        config = job.config

        print(f"🔄 Executing job: {config.name} ({job_id})")

        try:
            # Auto-apply ratio filter for volume_liquidity_balanced preset
            apply_filter = config.apply_ratio_filter or (
                config.preset_name == "volume_liquidity_balanced"
            )

            # Fetch token list
            if config.max_pages > 1:
                response = await fetch_all_pages(
                    config.params,
                    config.chain,
                    config.max_pages,
                    apply_filter,
                    config.min_ratio,
                    config.max_ratio
                )
            else:
                response = await fetch_token_list(
                    config.params,
                    config.chain,
                    apply_filter,
                    config.min_ratio,
                    config.max_ratio
                )

            # Update job stats
            job.run_count += 1
            config.last_run = datetime.now(timezone.utc)
            config.last_status = JobStatus.ACTIVE

            # Store result
            result = {
                "job_id": job_id,
                "timestamp": response.fetch_timestamp,
                "token_count": response.total_fetched,
                "has_next": response.has_next,
                "tokens": [t.dict() for t in response.items[:10]]  # Store sample
            }

            job.results_history.append(result)
            if len(job.results_history) > self.max_history:
                job.results_history.pop(0)

            # Save full results to file
            result_file = os.path.join(
                self.results_dir,
                f"{job_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
            )
            with open(result_file, 'w') as f:
                json.dump({
                    "job_config": config.dict(),
                    "response": response.dict()
                }, f, indent=2, default=str)

            print(f"✅ Job {job_id} completed: {response.total_fetched} tokens fetched")

            if config.callback and config.callback in self.callbacks:
                try:
                    await self.callbacks[config.callback](response)
                    print(f"✅ Callback {config.callback} executed")
                except Exception as e:
                    print(f"⚠️ Callback {config.callback} failed: {str(e)}")

        except Exception as e:
            print(f"❌ Job {job_id} failed: {str(e)}")
            job.error_count += 1
            config.last_status = JobStatus.ERROR
            config.last_error = str(e)

    def add_job(
        self,
        job_id: str,
        name: str,
        params: TokenListParams,
        interval_minutes: int = 5,
        chain: str = "solana",
        max_pages: int = 1,
        description: Optional[str] = None,
        callback: Optional[str] = None,
        apply_ratio_filter: bool = False,
        min_ratio: float = 1.5,
        max_ratio: float = 6.0,
        preset_name: Optional[str] = None
    ) -> TokenListJob:
        """
        Add a new scheduled job

        Args:
            job_id: Unique identifier for the job
            name: Human-readable name for the job
            params: Token list parameters
            interval_minutes: Interval between runs (1-1440 minutes)
            chain: Blockchain to query
            max_pages: Maximum pages to fetch per run
            description: Optional job description
            callback: Optional callback function name
            apply_ratio_filter: Apply volume/liquidity ratio filtering
            min_ratio: Minimum volume/liquidity ratio
            max_ratio: Maximum volume/liquidity ratio
            preset_name: Name of preset used (for auto filtering)

        Returns:
            The created TokenListJob
        """
        if job_id in self.jobs:
            raise ValueError(f"Job {job_id} already exists")

        # Auto-enable ratio filter for volume_liquidity_balanced preset
        if preset_name == "volume_liquidity_balanced":
            apply_ratio_filter = True

        # Create job configuration
        config = JobConfig(
            job_id=job_id,
            name=name,
            description=description,
            params=params,
            chain=chain,
            interval_minutes=interval_minutes,
            max_pages=max_pages,
            callback=callback,
            apply_ratio_filter=apply_ratio_filter,
            min_ratio=min_ratio,
            max_ratio=max_ratio,
            preset_name=preset_name
        )

        # Create job wrapper
        job = TokenListJob(config=config)

        # Add to scheduler if running
        if self._running:
            apscheduler_job = self.scheduler.add_job(
                self._execute_job,
                'interval',
                minutes=interval_minutes,
                args=[job_id],
                id=f"token_list_{job_id}",
                name=name,
                max_instances=1,
                coalesce=True
            )
            job.apscheduler_job_id = apscheduler_job.id

        self.jobs[job_id] = job
        print(f"✅ Added job: {name} ({job_id}) - "
              f"Interval: {interval_minutes} minutes")

        return job

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a scheduled job

        Args:
            job_id: ID of the job to remove

        Returns:
            True if job was removed, False if not found
        """
        if job_id not in self.jobs:
            return False

        job = self.jobs[job_id]

        if job.apscheduler_job_id and self._running:
            try:
                self.scheduler.remove_job(job.apscheduler_job_id)
            except Exception:
                pass

        del self.jobs[job_id]
        print(f"✅ Removed job: {job_id}")
        return True

    def pause_job(self, job_id: str) -> bool:
        """
        Pause a scheduled job

        Args:
            job_id: ID of the job to pause

        Returns:
            True if job was paused, False if not found
        """
        if job_id not in self.jobs:
            return False

        job = self.jobs[job_id]
        if job.apscheduler_job_id and self._running:
            self.scheduler.pause_job(job.apscheduler_job_id)
            job.config.last_status = JobStatus.PAUSED
            print(f"⏸️ Paused job: {job_id}")
            return True

        return False

    def resume_job(self, job_id: str) -> bool:
        """
        Resume a paused job

        Args:
            job_id: ID of the job to resume

        Returns:
            True if job was resumed, False if not found
        """
        if job_id not in self.jobs:
            return False

        job = self.jobs[job_id]
        if job.apscheduler_job_id and self._running:
            self.scheduler.resume_job(job.apscheduler_job_id)
            job.config.last_status = JobStatus.ACTIVE
            print(f"▶️ Resumed job: {job_id}")
            return True

        return False

    async def run_job_once(self, job_id: str):
        """
        Run a job immediately (one-time execution)

        Args:
            job_id: ID of the job to run
        """
        await self._execute_job(job_id)

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status information for a job

        Args:
            job_id: ID of the job

        Returns:
            Dictionary with job status or None if not found
        """
        if job_id not in self.jobs:
            return None

        job = self.jobs[job_id]
        return {
            "job_id": job_id,
            "name": job.config.name,
            "status": job.config.last_status.value,
            "interval_minutes": job.config.interval_minutes,
            "run_count": job.run_count,
            "error_count": job.error_count,
            "last_run": job.config.last_run.isoformat() if job.config.last_run else None,
            "last_error": job.config.last_error,
            "created_at": job.config.created_at.isoformat()
        }

    def list_jobs(self) -> List[Dict[str, Any]]:
        """
        List all scheduled jobs

        Returns:
            List of job status dictionaries
        """
        return [self.get_job_status(job_id) for job_id in self.jobs.keys()]

    def start(self):
        """Start the scheduler"""
        if not self._running:
            # Add all existing jobs to scheduler
            for job_id, job in self.jobs.items():
                config = job.config
                apscheduler_job = self.scheduler.add_job(
                    self._execute_job,
                    'interval',
                    minutes=config.interval_minutes,
                    args=[job_id],
                    id=f"token_list_{job_id}",
                    name=config.name,
                    max_instances=1,
                    coalesce=True
                )
                job.apscheduler_job_id = apscheduler_job.id

            self.scheduler.start()
            self._running = True
            print("🚀 Scheduler started")

    def stop(self):
        """Stop the scheduler"""
        if self._running:
            self.scheduler.shutdown()
            self._running = False
            print("🛑 Scheduler stopped")


_scheduler_instance: Optional[TokenListScheduler] = None


def get_scheduler() -> TokenListScheduler:
    """Get or create the singleton scheduler instance"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = TokenListScheduler()
    return _scheduler_instance


if __name__ == "__main__":
    # Example usage
    async def example_callback(response: TokenListResponse):
        """Example callback that processes fetched tokens"""
        print(f"📊 Callback: Processing {len(response.items)} tokens")

    async def main():
        scheduler = get_scheduler()

        scheduler.register_callback("process_tokens", example_callback)

        scheduler.add_job(
            job_id="high_liquidity",
            name="High Liquidity Trending Tokens",
            params=TokenListPresets.high_liquidity_trending(),
            interval_minutes=5,
            callback="process_tokens",
            description="Fetch high liquidity tokens with volume increase"
        )

        scheduler.add_job(
            job_id="new_listings",
            name="New Token Listings",
            params=TokenListPresets.new_listings(),
            interval_minutes=10,
            description="Monitor newly listed tokens"
        )

        scheduler.start()

        print("\n📋 Active jobs:")
        for job in scheduler.list_jobs():
            print(f"  - {job['name']}: {job['status']}")

        print("\n🔄 Running high_liquidity job once...")
        await scheduler.run_job_once("high_liquidity")

        # Keep running for 30 seconds
        await asyncio.sleep(30)

        # Stop scheduler
        scheduler.stop()

    asyncio.run(main())