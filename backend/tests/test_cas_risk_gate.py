"""Proves the CAS Dislocation Engine's own arm switch actually gates
RiskEngine.process_decision for CAS_DISLOCATION-sourced decisions, and
that it's fully independent of the ALGO capital/pyramid gate and of
manual trading — enabling one must never enable another.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from backend.app.engines.algo_config import algo_config_state
from backend.app.engines.risk import RiskEngine
from backend.app.execution.risk_limits import RiskLimits
from backend.app.strategies.cas_dislocation.config_state import cas_config_state

GENEROUS_LIMITS = RiskLimits(max_quantity_per_order=10000)


@pytest.fixture(autouse=True)
def _reset_configs():
    cas_config_state.configure(underlying="NIFTY", lots=1)  # also disarms
    algo_config_state.configure(mode="SYSTEM")
    yield
    cas_config_state.configure(underlying="NIFTY", lots=1)
    algo_config_state.configure(mode="SYSTEM")


def _decision(**kw):
    d = {
        "decision_id": "DEC_1",
        "instrument": "NIFTY 24800 CE",
        "instrument_token": "NSE_FO|1",
        "action": "TRADE",
        "quantity": 65,
        "price": 80.0,
        "transaction_type": "BUY",
        "timestamp": datetime(2026, 1, 1, 11, 0),
        "source": "CAS_DISLOCATION",
    }
    d.update(kw)
    return d


async def _run(engine, decision):
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    with patch("backend.app.engines.risk.event_bus.publish", new=capture), \
         patch("backend.app.engines.risk.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 11, 0)
        await engine.process_decision(decision)

    return published


@pytest.mark.asyncio
async def test_cas_decision_rejected_when_not_enabled():
    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision())

    assert "EXECUTION_REQUEST" not in [t for t, _ in published]
    risk_decision = next(p for t, p in published if t == "RISK_DECISION")
    assert "CAS Dislocation Engine is not enabled" in risk_decision["reason"]


@pytest.mark.asyncio
async def test_cas_decision_passes_once_enabled():
    cas_config_state.enable()
    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision())

    assert "EXECUTION_REQUEST" in [t for t, _ in published]


@pytest.mark.asyncio
async def test_cas_enabled_does_not_enable_algo_decisions():
    cas_config_state.enable()  # CAS armed, ALGO stays default-disabled
    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision(source="ALGO"))

    assert "EXECUTION_REQUEST" not in [t for t, _ in published]
    risk_decision = next(p for t, p in published if t == "RISK_DECISION")
    assert "Algo trading is not enabled" in risk_decision["reason"]


@pytest.mark.asyncio
async def test_algo_enabled_does_not_enable_cas_decisions():
    algo_config_state.configure(mode="SYSTEM")
    algo_config_state.enable()  # ALGO armed, CAS stays default-disabled
    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision(source="CAS_DISLOCATION"))

    assert "EXECUTION_REQUEST" not in [t for t, _ in published]
    risk_decision = next(p for t, p in published if t == "RISK_DECISION")
    assert "CAS Dislocation Engine is not enabled" in risk_decision["reason"]


@pytest.mark.asyncio
async def test_manual_trading_decision_bypasses_cas_gate_even_when_disabled():
    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision(source="MANUAL_TRADING"))

    assert "EXECUTION_REQUEST" in [t for t, _ in published]
