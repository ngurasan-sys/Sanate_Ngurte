import logging

from fastapi import APIRouter, HTTPException

from backend.app.backtest.jobs import backtest_job_manager
from backend.app.backtest.models import BacktestRequest
from backend.app.backtest.strategies_catalog import STRATEGY_CATALOG

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])


@router.get("/strategies")
async def list_strategies():
    return [
        {"name": meta.name, "label": meta.label, "description": meta.description, "direction": meta.direction}
        for meta in STRATEGY_CATALOG.values()
    ]


@router.post("/run")
async def run_backtest(request: BacktestRequest):
    job = backtest_job_manager.start_job(request)
    return job


@router.get("/jobs")
async def list_jobs():
    return backtest_job_manager.list_jobs()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    try:
        return backtest_job_manager.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No backtest job {job_id!r}.")
