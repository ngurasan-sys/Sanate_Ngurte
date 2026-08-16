"""In-memory async job runner for backtests — same shape as every other
in-memory state holder in this codebase (algo_config_state,
manual_trading_engine.positions): resets on restart, deliberately no
persistence layer for a v1.

run_backtest is CPU-bound (pandas + numba), so it's run in a thread pool
executor rather than awaited directly — otherwise a multi-month backtest
would block the entire event loop, freezing every other websocket/API
consumer in the app for however long it takes to compute.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict

from .engine import run_backtest
from .models import BacktestJob, BacktestRequest

logger = logging.getLogger(__name__)


class BacktestJobManager:
    def __init__(self):
        self.jobs: Dict[str, BacktestJob] = {}

    def start_job(self, request: BacktestRequest) -> BacktestJob:
        job_id = f"BT_{uuid.uuid4().hex[:10]}"
        job = BacktestJob(job_id=job_id, status="PENDING", request=request, created_at=datetime.now())
        self.jobs[job_id] = job
        asyncio.create_task(self._run(job_id))
        return job

    def get_job(self, job_id: str) -> BacktestJob:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def list_jobs(self):
        return list(self.jobs.values())

    async def _run(self, job_id: str) -> None:
        job = self.jobs[job_id]
        job.status = "RUNNING"
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, run_backtest, job.request)
            job.result = result
            job.status = "COMPLETED"
        except Exception as exc:
            logger.error(f"Backtest job {job_id} failed: {exc}")
            job.error = str(exc)
            job.status = "FAILED"
        finally:
            job.completed_at = datetime.now()


backtest_job_manager = BacktestJobManager()
