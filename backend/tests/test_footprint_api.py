from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.endpoints.footprint import router as footprint_router
from backend.app.order_flow.footprint_candle import FootprintCandleAggregator
from backend.app.order_flow.footprint_processor import footprint_processor

app = FastAPI()
app.include_router(footprint_router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_footprint_processor():
    """footprint_processor is a real module-level singleton, also started
    for real by any other test that spins up the full app via TestClient
    (unpatched) — e.g. a router-registration smoke test elsewhere in the
    suite can leave real mock-feed data sitting in its aggregator well
    before this file runs. Reset to a clean aggregator around every test
    so these tests can't observe state left over from anywhere else.
    """
    footprint_processor.aggregator = FootprintCandleAggregator()
    yield
    footprint_processor.aggregator = FootprintCandleAggregator()


def test_list_instruments_returns_the_three_seeded_futures():
    response = client.get("/api/v1/footprint/instruments")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"NIFTY FUT", "BANKNIFTY FUT", "SENSEX FUT"}


def test_list_timeframes_returns_configured_timeframes():
    response = client.get("/api/v1/footprint/timeframes")
    assert response.status_code == 200
    assert set(response.json()) == {"1m", "3m", "5m", "15m"}


def test_get_current_candle_404_when_no_data_yet():
    response = client.get("/api/v1/footprint/NIFTY FUT/5m")
    assert response.status_code == 404


def test_get_current_candle_422_for_unknown_timeframe():
    response = client.get("/api/v1/footprint/NIFTY FUT/7m")
    assert response.status_code == 422


def test_get_current_candle_returns_data_once_ticks_have_been_processed():
    footprint_processor.aggregator.process_tick(
        "NIFTY FUT", 24500.0, 100, "AGGRESSIVE_BUY", datetime.now(timezone.utc), "5m",
    )
    response = client.get("/api/v1/footprint/NIFTY FUT/5m")
    assert response.status_code == 200
    assert response.json()["close"] == 24500.0


def test_set_imbalance_ratio_updates_the_shared_processor():
    response = client.post("/api/v1/footprint/imbalance-ratio", json={"ratio_pct": 400.0})
    assert response.status_code == 200
    assert response.json() == {"ratio_pct": 400.0}
    assert footprint_processor.aggregator.imbalance_ratio_pct == 400.0


def test_set_imbalance_ratio_rejects_out_of_range_values():
    response = client.post("/api/v1/footprint/imbalance-ratio", json={"ratio_pct": 50.0})
    assert response.status_code == 422
