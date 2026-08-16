import asyncio
from datetime import date
from unittest.mock import patch

import pytest

from backend.app.backtest.jobs import BacktestJobManager
from backend.app.backtest.models import BacktestRequest, BacktestResult


def _request():
    return BacktestRequest(underlying="NIFTY", date_from=date(2024, 10, 1), date_to=date(2024, 10, 2))


def _fake_result(request):
    return BacktestResult(
        underlying=request.underlying, date_from=request.date_from, date_to=request.date_to,
        initial_cash=100000.0, final_equity=105000.0, total_return_pct=5.0,
        sharpe_ratio=1.2, max_drawdown_pct=-2.0, win_rate_pct=60.0,
        total_trades=3, trades=[], equity_curve=[],
    )


@pytest.mark.asyncio
async def test_job_completes_successfully():
    manager = BacktestJobManager()
    with patch("backend.app.backtest.jobs.run_backtest", side_effect=_fake_result):
        job = manager.start_job(_request())
        assert job.status == "PENDING"

        for _ in range(50):
            if manager.get_job(job.job_id).status in ("COMPLETED", "FAILED"):
                break
            await asyncio.sleep(0.05)

    final = manager.get_job(job.job_id)
    assert final.status == "COMPLETED"
    assert final.result is not None
    assert final.result.total_trades == 3
    assert final.completed_at is not None
    assert final.error is None


@pytest.mark.asyncio
async def test_job_failure_is_captured_not_raised():
    manager = BacktestJobManager()

    def _boom(request):
        raise ValueError("no data for this range")

    with patch("backend.app.backtest.jobs.run_backtest", side_effect=_boom):
        job = manager.start_job(_request())

        for _ in range(50):
            if manager.get_job(job.job_id).status in ("COMPLETED", "FAILED"):
                break
            await asyncio.sleep(0.05)

    final = manager.get_job(job.job_id)
    assert final.status == "FAILED"
    assert final.result is None
    assert "no data for this range" in final.error


def test_get_unknown_job_raises_keyerror():
    manager = BacktestJobManager()
    with pytest.raises(KeyError):
        manager.get_job("BT_doesnotexist")


@pytest.mark.asyncio
async def test_list_jobs_returns_all():
    manager = BacktestJobManager()
    with patch("backend.app.backtest.jobs.run_backtest", side_effect=_fake_result):
        job1 = manager.start_job(_request())
        job2 = manager.start_job(_request())
        await asyncio.sleep(0.1)

    ids = {j.job_id for j in manager.list_jobs()}
    assert {job1.job_id, job2.job_id} <= ids
