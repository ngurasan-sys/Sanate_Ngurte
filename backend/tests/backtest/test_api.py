import asyncio
from datetime import date
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.endpoints.backtest import router as backtest_router
from backend.app.backtest.jobs import backtest_job_manager
from backend.app.backtest.models import BacktestResult

app = FastAPI()
app.include_router(backtest_router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_jobs():
    backtest_job_manager.jobs.clear()
    yield
    backtest_job_manager.jobs.clear()


def _fake_result(request):
    return BacktestResult(
        underlying=request.underlying, date_from=request.date_from, date_to=request.date_to,
        initial_cash=100000.0, final_equity=101000.0, total_return_pct=1.0,
        sharpe_ratio=0.5, max_drawdown_pct=-1.0, win_rate_pct=50.0,
        total_trades=1, trades=[], equity_curve=[],
    )


def test_run_endpoint_creates_pending_job():
    with patch("backend.app.backtest.jobs.run_backtest", side_effect=_fake_result):
        response = client.post("/api/v1/backtest/run", json={
            "underlying": "NIFTY", "date_from": "2024-10-01", "date_to": "2024-10-02",
        })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("PENDING", "RUNNING", "COMPLETED")
    assert body["job_id"].startswith("BT_")


def test_job_reaches_completed_via_get_endpoint():
    with patch("backend.app.backtest.jobs.run_backtest", side_effect=_fake_result):
        response = client.post("/api/v1/backtest/run", json={
            "underlying": "NIFTY", "date_from": "2024-10-01", "date_to": "2024-10-02",
        })
        job_id = response.json()["job_id"]

        for _ in range(50):
            status_response = client.get(f"/api/v1/backtest/jobs/{job_id}")
            if status_response.json()["status"] in ("COMPLETED", "FAILED"):
                break

    final = client.get(f"/api/v1/backtest/jobs/{job_id}").json()
    assert final["status"] == "COMPLETED"
    assert final["result"]["total_trades"] == 1


def test_get_unknown_job_returns_404():
    response = client.get("/api/v1/backtest/jobs/BT_missing")
    assert response.status_code == 404


def test_list_jobs_endpoint():
    with patch("backend.app.backtest.jobs.run_backtest", side_effect=_fake_result):
        client.post("/api/v1/backtest/run", json={
            "underlying": "NIFTY", "date_from": "2024-10-01", "date_to": "2024-10-02",
        })

    response = client.get("/api/v1/backtest/jobs")
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_run_endpoint_validates_request_body():
    response = client.post("/api/v1/backtest/run", json={"underlying": "NIFTY"})  # missing dates
    assert response.status_code == 422


def test_run_endpoint_rejects_unknown_strategy():
    response = client.post("/api/v1/backtest/run", json={
        "underlying": "NIFTY", "date_from": "2024-10-01", "date_to": "2024-10-02", "strategy": "NOT_REAL",
    })
    assert response.status_code == 422


def test_strategies_endpoint_lists_all_catalog_entries():
    response = client.get("/api/v1/backtest/strategies")
    assert response.status_code == 200
    body = response.json()
    names = {s["name"] for s in body}
    assert names == {"SHORT_STRADDLE", "LONG_STRADDLE", "LONG_CE_MOMENTUM", "LONG_PE_MOMENTUM"}
    for strategy in body:
        assert strategy["direction"] in ("shortonly", "longonly")
        assert strategy["label"]
        assert strategy["description"]
