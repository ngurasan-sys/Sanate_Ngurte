"""Endpoint-level tests for /api/v1/strategy-control/* — start performs
real readiness checks (never a cosmetic frontend-only toggle), stop never
touches an open position, and start-all validates each strategy
independently rather than failing the whole operation on one blocker.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.endpoints import strategies as strategies_module
from backend.app.api.endpoints.strategies import register_strategy, router as strategies_router
from backend.app.api.endpoints.strategy_control import router as strategy_control_router
from backend.app.core.active_broker import active_broker
from backend.app.engines.execution import execution_engine
from backend.app.engines.risk import risk_engine
from backend.app.engines.strategy_runtime import strategy_runtime

app = FastAPI()
app.include_router(strategies_router)
app.include_router(strategy_control_router)
client = TestClient(app)


class _FakeEngine:
    """Minimal stand-in with no .positions/.config — exercises the
    'engine has no config' readiness branch without touching a real
    strategy engine's internal state machine."""
    pass


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    strategies_module._strategy_registry.clear()
    register_strategy("test_strategy", "Test Strategy", "A strategy for tests.", engine=_FakeEngine())

    for sid in list(strategy_runtime.get_all().keys()):
        strategy_runtime._states.pop(sid, None)
    monkeypatch.setattr(strategy_runtime, "_persist", lambda: None)

    monkeypatch.setattr(risk_engine, "_started", True)
    monkeypatch.setattr(execution_engine, "_started", True)

    yield

    strategies_module._strategy_registry.clear()
    for sid in list(strategy_runtime.get_all().keys()):
        strategy_runtime._states.pop(sid, None)


def _make_broker_ready(monkeypatch):
    monkeypatch.setattr(active_broker, "get_active_broker_id", lambda: "upstox")
    monkeypatch.setattr(active_broker, "is_broker_ready", lambda bid: True)
    monkeypatch.setattr(active_broker, "get_active_provider", lambda: object())


def test_unknown_strategy_returns_404():
    response = client.post("/api/v1/strategy-control/does_not_exist/start")
    assert response.status_code == 404


def test_start_rejected_when_execution_mode_disabled():
    response = client.post("/api/v1/strategy-control/test_strategy/start")
    assert response.status_code == 400
    assert "DISABLED" in response.json()["detail"]


def test_start_blocked_when_no_active_broker(monkeypatch):
    monkeypatch.setattr(active_broker, "get_active_broker_id", lambda: None)
    client.post("/api/v1/strategy-control/test_strategy/execution-mode", json={"mode": "ALGO"})

    response = client.post("/api/v1/strategy-control/test_strategy/start")
    assert response.status_code == 409
    assert "Active broker" in response.json()["detail"]
    assert strategy_runtime.get("test_strategy").status == "BLOCKED"


def test_start_blocked_when_risk_engine_not_running(monkeypatch):
    _make_broker_ready(monkeypatch)
    monkeypatch.setattr(risk_engine, "_started", False)
    client.post("/api/v1/strategy-control/test_strategy/execution-mode", json={"mode": "ALGO"})

    response = client.post("/api/v1/strategy-control/test_strategy/start")
    assert response.status_code == 409
    assert "Risk engine" in response.json()["detail"]


def test_start_succeeds_when_all_checks_pass(monkeypatch):
    _make_broker_ready(monkeypatch)
    client.post("/api/v1/strategy-control/test_strategy/execution-mode", json={"mode": "PAPER"})

    response = client.post("/api/v1/strategy-control/test_strategy/start")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "RUNNING"
    assert body["enabled"] is True


def test_stop_never_reports_position_closed(monkeypatch):
    """Verifies STOP's response reflects POSITION_ACTIVE (not OFF) when an
    open position exists — proving the endpoint doesn't silently discard
    that state."""
    _make_broker_ready(monkeypatch)
    client.post("/api/v1/strategy-control/test_strategy/execution-mode", json={"mode": "ALGO"})
    client.post("/api/v1/strategy-control/test_strategy/start")

    fake_engine = _FakeEngine()
    fake_engine.positions = {"p1": {"is_active": True}}
    strategies_module._strategy_registry["test_strategy"]["engine"] = fake_engine

    response = client.post("/api/v1/strategy-control/test_strategy/stop")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["status"] == "POSITION_ACTIVE"


def test_execution_mode_and_trading_mode_are_mutually_exclusive_single_fields():
    r1 = client.post("/api/v1/strategy-control/test_strategy/execution-mode", json={"mode": "ALGO"})
    assert r1.json()["execution_mode"] == "ALGO"

    r2 = client.post("/api/v1/strategy-control/test_strategy/execution-mode", json={"mode": "PAPER"})
    # ALGO is structurally gone the moment PAPER is set — single field.
    assert r2.json()["execution_mode"] == "PAPER"

    r3 = client.post("/api/v1/strategy-control/test_strategy/trading-mode", json={"mode": "MANUAL"})
    assert r3.json()["trading_mode"] == "MANUAL"


def test_start_all_validates_each_strategy_independently(monkeypatch):
    _make_broker_ready(monkeypatch)
    register_strategy("blocked_strategy", "Blocked Strategy", "Will fail readiness.", engine=_FakeEngine())

    client.post("/api/v1/strategy-control/test_strategy/execution-mode", json={"mode": "ALGO"})
    # blocked_strategy stays DISABLED on purpose

    response = client.post("/api/v1/strategy-control/start-all")
    assert response.status_code == 200
    body = response.json()

    assert body["test_strategy"]["started"] is True
    assert body["blocked_strategy"]["started"] is False
    assert "DISABLED" in body["blocked_strategy"]["reason"]


def test_get_strategies_reflects_runtime_state(monkeypatch):
    _make_broker_ready(monkeypatch)
    client.post("/api/v1/strategy-control/test_strategy/execution-mode", json={"mode": "ALGO"})
    client.post("/api/v1/strategy-control/test_strategy/trading-mode", json={"mode": "MANUAL"})
    client.post("/api/v1/strategy-control/test_strategy/start")

    response = client.get("/api/v1/strategies")
    body = response.json()
    strat = next(s for s in body["strategies"] if s["id"] == "test_strategy")

    assert strat["enabled"] is True
    assert strat["status"] == "RUNNING"
    assert strat["executionMode"] == "ALGO"
    assert strat["tradingMode"] == "MANUAL"
