import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.endpoints.execution_control import router as execution_control_router
from backend.app.engines.risk import risk_engine
from backend.app.execution.runtime_state import execution_runtime_state

app = FastAPI()
app.include_router(execution_control_router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_state():
    execution_runtime_state.disarm()
    risk_engine.resume()
    yield
    execution_runtime_state.disarm()
    risk_engine.resume()


def test_status_reports_disarmed_dry_run_by_default(monkeypatch):
    monkeypatch.delenv("UPSTOX_EXECUTION_MODE", raising=False)

    response = client.get("/api/v1/execution/status")

    assert response.status_code == 200
    body = response.json()
    assert body["env_mode"] == "DRY_RUN"
    assert body["resolved_mode"] == "DRY_RUN"
    assert body["armed"] is False
    assert body["armed_at"] is None
    assert body["halted_reason"] is None


def test_arm_rejects_wrong_confirmation_phrase():
    response = client.post("/api/v1/execution/arm", json={"confirm": "yes please"})

    assert response.status_code == 400
    assert execution_runtime_state.is_armed() is False


def test_arm_with_exact_phrase_arms_and_reports_it():
    response = client.post(
        "/api/v1/execution/arm", json={"confirm": "ARM LIVE TRADING", "note": "manual test"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["armed"] is True
    assert body["armed_at"] is not None
    assert body["armed_note"] == "manual test"
    assert execution_runtime_state.is_armed() is True


def test_disarm_clears_the_switch():
    execution_runtime_state.arm(note="x")

    response = client.post("/api/v1/execution/disarm")

    assert response.status_code == 200
    assert response.json()["armed"] is False
    assert execution_runtime_state.is_armed() is False


def test_halt_sets_kill_switch_reason_and_resume_clears_it():
    halt_response = client.post("/api/v1/execution/halt", json={"reason": "manual stop"})
    assert halt_response.status_code == 200
    assert halt_response.json()["halted_reason"] == "manual stop"
    assert risk_engine.state.halted_reason == "manual stop"

    resume_response = client.post("/api/v1/execution/resume")
    assert resume_response.status_code == 200
    assert resume_response.json()["halted_reason"] is None
    assert risk_engine.state.halted_reason is None


def test_status_includes_risk_limits_and_state():
    response = client.get("/api/v1/execution/status")
    body = response.json()

    assert "max_quantity_per_order" in body["risk_limits"]
    assert "max_daily_orders" in body["risk_limits"]
    assert "open_positions" in body["risk_state"]
    assert "orders_placed_today" in body["risk_state"]
