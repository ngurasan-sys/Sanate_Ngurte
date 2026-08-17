"""Proves the OFAO mock-footprint-data safety gate actually works:
mock data must never let an OFAO decision reach a real order once LIVE is
armed, but must never block harmless DRY_RUN/SANDBOX simulation either.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from backend.app.engines.algo_config import algo_config_state
from backend.app.engines.risk import RiskEngine
from backend.app.execution.risk_limits import RiskLimits
from backend.app.order_flow.footprint_processor import footprint_processor
from backend.app.strategies.order_flow_absorption.config import OFAOConfig
from backend.app.strategies.order_flow_absorption.engine import ofao_engine

GENEROUS_LIMITS = RiskLimits(max_quantity_per_order=10000)


@pytest.fixture(autouse=True)
def _reset_configs():
    ofao_engine.configure(OFAOConfig())
    ofao_engine.enable()
    algo_config_state.configure(mode="SYSTEM")
    original_source = footprint_processor.data_source
    yield
    ofao_engine.configure(OFAOConfig())
    footprint_processor.data_source = original_source


def _decision(**kw):
    d = {
        "decision_id": "OFAO_BLOCK_TEST_001",
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
async def test_ofao_live_blocked_when_footprint_data_is_mock():
    footprint_processor.data_source = "MOCK"
    with patch("backend.app.engines.risk.resolve_mode") as mock_resolve:
        from backend.app.execution.order_gateway import ExecutionMode
        mock_resolve.return_value = ExecutionMode.LIVE

        engine = RiskEngine(GENEROUS_LIMITS)
        published = await _run(engine, _decision())

        assert "EXECUTION_REQUEST" not in [t for t, _ in published]
        risk_decision = next(p for t, p in published if t == "RISK_DECISION")
        assert "OFAO LIVE = BLOCKED" in risk_decision["reason"]


@pytest.mark.asyncio
async def test_ofao_dry_run_not_blocked_by_mock_data():
    """The gate only blocks the LIVE path — harmless simulation must keep
    working even with mock data, since that's the whole point of DRY_RUN."""
    footprint_processor.data_source = "MOCK"
    with patch("backend.app.engines.risk.resolve_mode") as mock_resolve:
        from backend.app.execution.order_gateway import ExecutionMode
        mock_resolve.return_value = ExecutionMode.DRY_RUN

        engine = RiskEngine(GENEROUS_LIMITS)
        published = await _run(engine, _decision())

        assert "EXECUTION_REQUEST" in [t for t, _ in published]


@pytest.mark.asyncio
async def test_ofao_live_allowed_once_data_source_is_real():
    footprint_processor.data_source = "REAL"
    with patch("backend.app.engines.risk.resolve_mode") as mock_resolve:
        from backend.app.execution.order_gateway import ExecutionMode
        mock_resolve.return_value = ExecutionMode.LIVE

        engine = RiskEngine(GENEROUS_LIMITS)
        published = await _run(engine, _decision())

        assert "EXECUTION_REQUEST" in [t for t, _ in published]
