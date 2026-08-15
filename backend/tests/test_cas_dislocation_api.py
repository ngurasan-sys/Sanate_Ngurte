import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.endpoints.cas_dislocation import router as cas_router
from backend.app.strategies.cas_dislocation.config_state import cas_config_state
from backend.app.strategies.cas_dislocation.engine import cas_dislocation_engine

app = FastAPI()
app.include_router(cas_router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_state():
    cas_config_state.configure(underlying="NIFTY", lots=1)
    cas_dislocation_engine.positions.clear()
    cas_dislocation_engine.latest_reading = None
    yield
    cas_config_state.configure(underlying="NIFTY", lots=1)
    cas_dislocation_engine.positions.clear()


def test_get_config_defaults():
    response = client.get("/api/v1/cas-dislocation/config")
    assert response.status_code == 200
    body = response.json()
    assert body["underlying"] == "NIFTY"
    assert body["enabled"] is False


def test_configure_success():
    response = client.post("/api/v1/cas-dislocation/configure", json={
        "underlying": "SENSEX", "lots": 3, "max_hold_seconds": 120,
        "min_score_to_alert": 50, "min_score_to_execute": 90, "auto_execute": True,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["underlying"] == "SENSEX"
    assert body["lots"] == 3
    assert body["auto_execute"] is True
    assert body["enabled"] is False


def test_configure_invalid_underlying_returns_400():
    response = client.post("/api/v1/cas-dislocation/configure", json={"underlying": "FINNIFTY", "lots": 1})
    assert response.status_code == 400
    assert "Unsupported underlying" in response.json()["detail"]


def test_enable_disable_roundtrip():
    enable_response = client.post("/api/v1/cas-dislocation/enable")
    assert enable_response.status_code == 200
    assert enable_response.json()["enabled"] is True

    disable_response = client.post("/api/v1/cas-dislocation/disable")
    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False


def test_get_reading_none_initially():
    response = client.get("/api/v1/cas-dislocation/reading")
    assert response.status_code == 200
    assert response.json() is None


def test_list_positions_empty_initially():
    response = client.get("/api/v1/cas-dislocation/positions")
    assert response.status_code == 200
    assert response.json() == []


def test_execute_endpoint_no_signal_returns_400():
    response = client.post("/api/v1/cas-dislocation/execute")
    assert response.status_code == 400
    assert "No active signal" in response.json()["detail"]
