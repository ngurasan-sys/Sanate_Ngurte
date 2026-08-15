import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.endpoints.algo_config import router as algo_config_router
from backend.app.engines.algo_config import algo_config_state

app = FastAPI()
app.include_router(algo_config_router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_state():
    algo_config_state.configure(mode="SYSTEM")
    yield
    algo_config_state.configure(mode="SYSTEM")


def test_status_defaults_to_system_disabled():
    response = client.get("/api/v1/algo-config/status")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "SYSTEM"
    assert body["enabled"] is False


def test_configure_system_mode():
    response = client.post("/api/v1/algo-config/configure", json={"mode": "SYSTEM"})
    assert response.status_code == 200
    assert response.json()["mode"] == "SYSTEM"


def test_configure_manual_mode_success():
    response = client.post("/api/v1/algo-config/configure", json={
        "mode": "MANUAL", "underlying": "NIFTY", "capital": 100000.0,
        "lot_schedule": [2, 3, 5], "stop_loss_pct": 30.0, "target_pct": 50.0,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "MANUAL"
    assert body["capital"] == 100000.0
    assert body["lot_schedule"] == [2, 3, 5]
    assert body["enabled"] is False


def test_configure_manual_mode_missing_capital_returns_400():
    response = client.post("/api/v1/algo-config/configure", json={
        "mode": "MANUAL", "underlying": "NIFTY", "lot_schedule": [2],
    })
    assert response.status_code == 400
    assert "capital" in response.json()["detail"]


def test_enable_and_disable_roundtrip():
    client.post("/api/v1/algo-config/configure", json={
        "mode": "MANUAL", "underlying": "NIFTY", "capital": 1000.0, "lot_schedule": [1],
    })

    enable_response = client.post("/api/v1/algo-config/enable")
    assert enable_response.status_code == 200
    assert enable_response.json()["enabled"] is True

    disable_response = client.post("/api/v1/algo-config/disable")
    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False


def test_reconfigure_disarms_via_api():
    client.post("/api/v1/algo-config/configure", json={
        "mode": "MANUAL", "underlying": "NIFTY", "capital": 1000.0, "lot_schedule": [1],
    })
    client.post("/api/v1/algo-config/enable")

    response = client.post("/api/v1/algo-config/configure", json={
        "mode": "MANUAL", "underlying": "NIFTY", "capital": 2000.0, "lot_schedule": [2],
    })
    assert response.json()["enabled"] is False
