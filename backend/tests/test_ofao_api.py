import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.endpoints.ofao import router as ofao_router
from backend.app.strategies.order_flow_absorption.config import OFAOConfig
from backend.app.strategies.order_flow_absorption.engine import ofao_engine

app = FastAPI()
app.include_router(ofao_router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    ofao_engine.configure(OFAOConfig())
    yield
    ofao_engine.configure(OFAOConfig())


def test_get_config_returns_the_default_disabled_config():
    response = client.get("/api/v1/ofao/config")
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_configure_replaces_the_config_and_disarms():
    ofao_engine.enable()
    response = client.post("/api/v1/ofao/configure", json={"absorption_strength_threshold": 80.0})
    assert response.status_code == 200
    body = response.json()
    assert body["absorption_strength_threshold"] == 80.0
    assert body["enabled"] is False  # reconfiguring always disarms


def test_configure_rejects_invalid_config():
    response = client.post("/api/v1/ofao/configure", json={"imbalance_ratio_pct": 250.0})
    assert response.status_code == 400


def test_enable_and_disable_round_trip():
    response = client.post("/api/v1/ofao/enable")
    assert response.json()["enabled"] is True

    response = client.post("/api/v1/ofao/disable")
    assert response.json()["enabled"] is False


def test_get_state_404_before_any_evaluation():
    response = client.get("/api/v1/ofao/state/NIFTY FUT")
    assert response.status_code == 404


def test_get_state_returns_snapshot_once_available():
    ofao_engine._latest_snapshot["NIFTY FUT"] = {"instrument_key": "NIFTY FUT", "state": "NO_SETUP"}
    response = client.get("/api/v1/ofao/state/NIFTY FUT")
    assert response.status_code == 200
    assert response.json()["state"] == "NO_SETUP"
