"""Proves OFAO's own arm switch (ofao_engine.config.enabled) actually
gates RiskEngine.process_decision for OFAO-sourced decisions, and that
it's fully independent of the ALGO capital/pyramid gate, CAS
Dislocation's gate, and manual trading — enabling one must never enable
another. Mirrors test_cas_risk_gate.py's structure exactly.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from backend.app.engines.algo_config import algo_config_state
from backend.app.engines.risk import RiskEngine
from backend.app.execution.risk_limits import RiskLimits
from backend.app.strategies.cas_dislocation.config_state import cas_config_state
from backend.app.strategies.order_flow_absorption.config import OFAOConfig
from backend.app.strategies.order_flow_absorption.engine import ofao_engine

GENEROUS_LIMITS = RiskLimits(max_quantity_per_order=10000)


@pytest.fixture(autouse=True)
def _reset_configs():
    ofao_engine.configure(OFAOConfig())  # also disarms
    algo_config_state.configure(mode="SYSTEM")
    yield
    ofao_engine.configure(OFAOConfig())
    algo_config_state.configure(mode="SYSTEM")


def _decision(**kw):
    d = {
        "decision_id": "OFAO_NIFTY_2026-01-01_110000_BULL_001",
        "instrument": "NIFTY 25000 CE",
        "instrument_token": "NSE_FO|1",
        "action": "TRADE",
        "quantity": 65,
        "price": 100.0,
        "transaction_type": "BUY",
        "timestamp": datetime(2026, 1, 1, 11, 0),
        "source": "OFAO",
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
async def test_ofao_decision_rejected_when_not_enabled():
    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision())

    assert "EXECUTION_REQUEST" not in [t for t, _ in published]
    risk_decision = next(p for t, p in published if t == "RISK_DECISION")
    assert "OFAO is not enabled" in risk_decision["reason"]


@pytest.mark.asyncio
async def test_ofao_decision_passes_once_enabled():
    ofao_engine.enable()
    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision())

    assert "EXECUTION_REQUEST" in [t for t, _ in published]


@pytest.mark.asyncio
async def test_ofao_enabled_does_not_enable_algo_decisions():
    ofao_engine.enable()  # OFAO armed, ALGO stays default-disabled
    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision(source="ALGO"))

    assert "EXECUTION_REQUEST" not in [t for t, _ in published]
    risk_decision = next(p for t, p in published if t == "RISK_DECISION")
    assert "Algo trading is not enabled" in risk_decision["reason"]


@pytest.mark.asyncio
async def test_algo_enabled_does_not_enable_ofao_decisions():
    algo_config_state.configure(mode="SYSTEM")
    algo_config_state.enable()  # ALGO armed, OFAO stays default-disabled
    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision(source="OFAO"))

    assert "EXECUTION_REQUEST" not in [t for t, _ in published]
    risk_decision = next(p for t, p in published if t == "RISK_DECISION")
    assert "OFAO is not enabled" in risk_decision["reason"]


@pytest.mark.asyncio
async def test_ofao_enabled_does_not_enable_cas_decisions():
    ofao_engine.enable()  # OFAO armed, CAS stays default-disabled
    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision(source="CAS_DISLOCATION"))

    assert "EXECUTION_REQUEST" not in [t for t, _ in published]
    risk_decision = next(p for t, p in published if t == "RISK_DECISION")
    assert "CAS Dislocation Engine is not enabled" in risk_decision["reason"]


@pytest.mark.asyncio
async def test_manual_trading_decision_bypasses_ofao_gate_even_when_disabled():
    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision(source="MANUAL_TRADING"))

    assert "EXECUTION_REQUEST" in [t for t, _ in published]


@pytest.mark.asyncio
async def test_reconfiguring_ofao_disarms_it():
    ofao_engine.enable()
    assert ofao_engine.config.enabled is True
    ofao_engine.configure(OFAOConfig(absorption_strength_threshold=80.0))
    assert ofao_engine.config.enabled is False
