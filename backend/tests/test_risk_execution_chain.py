"""End-to-end tests for the DECISION -> RISK -> EXECUTION chain.

These verify the chain as actually wired, not each piece in isolation:
a rejected decision must never reach the execution engine, and a
DRY_RUN execution must never be reported as a real submission.
"""

from datetime import datetime, time
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.engines.algo_config import algo_config_state
from backend.app.engines.execution import ExecutionEngine
from backend.app.engines.risk import RiskEngine
from backend.app.execution.risk_limits import RiskLimits, RiskState


@pytest.fixture(autouse=True)
def _reset_algo_config():
    # These decisions default to source="ALGO" (no explicit source set),
    # so they're now also subject to the algo-enabled gate added alongside
    # AlgoTradingConfig. SYSTEM mode + enabled reproduces this file's
    # original assumption (any approved TRADE decision reaches execution)
    # without needing a capital budget or pyramid schedule.
    algo_config_state.configure(mode="SYSTEM")
    algo_config_state.enable()
    yield
    algo_config_state.configure(mode="SYSTEM")


def _decision(**kw):
    d = {
        "decision_id": "DEC_1",
        "instrument": "NIFTY",
        "instrument_token": "NSE_FO|12345",
        "action": "TRADE",
        "quantity": 50,
        "transaction_type": "BUY",
        "timestamp": datetime(2026, 1, 1, 11, 0),
    }
    d.update(kw)
    return d


@pytest.mark.asyncio
async def test_rejected_decision_never_reaches_execution():
    """The whole point of the risk gate: a blocked decision must not
    produce an EXECUTION_REQUEST at all."""
    engine = RiskEngine(RiskLimits(max_quantity_per_order=10))  # 50 > 10
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    with patch("backend.app.engines.risk.event_bus.publish", new=capture):
        await engine.process_decision(_decision(quantity=50))

    topics = [t for t, _ in published]
    assert "RISK_DECISION" in topics
    assert "EXECUTION_REQUEST" not in topics

    risk_payload = next(p for t, p in published if t == "RISK_DECISION")
    assert risk_payload["approved"] is False
    assert "exceeds max_quantity_per_order" in risk_payload["reason"]


@pytest.mark.asyncio
async def test_non_trade_action_is_rejected():
    engine = RiskEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    with patch("backend.app.engines.risk.event_bus.publish", new=capture):
        await engine.process_decision(_decision(action="WAIT"))

    assert "EXECUTION_REQUEST" not in [t for t, _ in published]


@pytest.mark.asyncio
async def test_approved_decision_forwards_execution_request_with_token():
    engine = RiskEngine(RiskLimits())
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    # Force an in-session time so the market-hours check passes regardless
    # of when the suite actually runs.
    with patch("backend.app.engines.risk.event_bus.publish", new=capture), \
         patch("backend.app.engines.risk.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 11, 0)
        await engine.process_decision(_decision())

    exec_req = next(p for t, p in published if t == "EXECUTION_REQUEST")
    assert exec_req["instrument_token"] == "NSE_FO|12345"
    assert exec_req["quantity"] == 50
    assert exec_req["transaction_type"] == "BUY"


@pytest.mark.asyncio
async def test_daily_order_count_only_counts_real_submissions():
    """DRY_RUN and rejected orders must not consume the daily budget."""
    engine = RiskEngine()

    await engine.record_execution({"status": "DRY_RUN"})
    await engine.record_execution({"status": "REJECTED"})
    await engine.record_execution({"status": "ERROR"})
    assert engine.state.orders_placed_today == 0

    await engine.record_execution({"status": "SUBMITTED"})
    assert engine.state.orders_placed_today == 1


@pytest.mark.asyncio
async def test_halt_blocks_all_subsequent_decisions():
    engine = RiskEngine()
    engine.halt("manual kill")
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    with patch("backend.app.engines.risk.event_bus.publish", new=capture):
        await engine.process_decision(_decision())

    assert "EXECUTION_REQUEST" not in [t for t, _ in published]
    risk_payload = next(p for t, p in published if t == "RISK_DECISION")
    assert "manual kill" in risk_payload["reason"]

    engine.resume()
    assert engine.state.halted_reason is None


@pytest.mark.asyncio
async def test_execution_without_instrument_token_is_rejected_not_submitted():
    engine = ExecutionEngine()
    published = []

    async def capture(topic, payload):
        published.append(payload)

    with patch("backend.app.engines.execution.event_bus.publish", new=capture):
        await engine.execute_order({
            "instrument": "NIFTY", "decision_id": "DEC_1", "quantity": 50,
        })

    assert published[0]["status"] == "REJECTED"
    assert published[0]["order_id"] is None


@pytest.mark.asyncio
async def test_execution_in_dry_run_reports_dry_run_not_submitted(monkeypatch):
    monkeypatch.delenv("EXECUTION_MODE", raising=False)
    engine = ExecutionEngine()
    published = []

    async def capture(topic, payload):
        published.append(payload)

    with patch("backend.app.engines.execution.event_bus.publish", new=capture):
        await engine.execute_order({
            "instrument": "NIFTY",
            "instrument_token": "NSE_FO|12345",
            "decision_id": "DEC_1",
            "quantity": 50,
        })

    assert published[0]["status"] == "DRY_RUN"
    assert published[0]["mode"] == "DRY_RUN"
    assert published[0]["order_id"] is None
