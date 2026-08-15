"""Proves the algo capital budget / pyramid tier schedule actually gates
RiskEngine.process_decision for ALGO-sourced decisions, and — just as
important — that manual_trading orders are never subject to it. Same
"chain the real engine, patch event_bus.publish" style as
test_risk_execution_chain.py.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from backend.app.engines.algo_config import algo_config_state
from backend.app.engines.risk import RiskEngine
from backend.app.execution.risk_limits import RiskLimits

# Default RiskLimits.max_quantity_per_order is 100; every decision here
# requests 130+ (2+ NIFTY lots), so tests use a generous cap — the point
# of these tests is the algo-specific checks, not the universal quantity cap.
GENEROUS_LIMITS = RiskLimits(max_quantity_per_order=10000)


@pytest.fixture(autouse=True)
def _reset_algo_config():
    algo_config_state.configure(mode="SYSTEM")  # also disarms
    yield
    algo_config_state.configure(mode="SYSTEM")


def _decision(**kw):
    d = {
        "decision_id": "DEC_1",
        "instrument": "NIFTY 24500 CE",
        "instrument_token": "NSE_FO|1",
        "action": "TRADE",
        "quantity": 130,  # 2 lots of NIFTY (65)
        "price": 100.0,
        "transaction_type": "BUY",
        "timestamp": datetime(2026, 1, 1, 11, 0),
        "source": "ALGO",
    }
    d.update(kw)
    return d


async def _run(engine, decision, mock_now=datetime(2026, 1, 1, 11, 0)):
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    with patch("backend.app.engines.risk.event_bus.publish", new=capture), \
         patch("backend.app.engines.risk.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        await engine.process_decision(decision)

    return published


@pytest.mark.asyncio
async def test_algo_decision_rejected_when_algo_trading_not_enabled():
    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision())

    assert "EXECUTION_REQUEST" not in [t for t, _ in published]
    risk_decision = next(p for t, p in published if t == "RISK_DECISION")
    assert risk_decision["approved"] is False
    assert "not enabled" in risk_decision["reason"]


@pytest.mark.asyncio
async def test_algo_decision_passes_in_system_mode_once_enabled():
    algo_config_state.configure(mode="SYSTEM")
    algo_config_state.enable()

    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision())

    assert "EXECUTION_REQUEST" in [t for t, _ in published]


@pytest.mark.asyncio
async def test_algo_decision_within_manual_budget_and_tier_passes():
    algo_config_state.configure(
        mode="MANUAL", underlying="NIFTY", capital=100000.0, lot_schedule=[2, 3],
    )
    algo_config_state.enable()

    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision(quantity=130))  # tier 1: 2 lots = 130 qty

    assert "EXECUTION_REQUEST" in [t for t, _ in published]


@pytest.mark.asyncio
async def test_algo_decision_over_capital_budget_rejected():
    algo_config_state.configure(
        mode="MANUAL", underlying="NIFTY", capital=1000.0, lot_schedule=[2, 3],
    )
    algo_config_state.enable()

    engine = RiskEngine(GENEROUS_LIMITS)
    # quantity=130 * price=100 = 13000 > 1000 budget
    published = await _run(engine, _decision(quantity=130, price=100.0))

    assert "EXECUTION_REQUEST" not in [t for t, _ in published]
    risk_decision = next(p for t, p in published if t == "RISK_DECISION")
    assert "exceeding the configured budget" in risk_decision["reason"]


@pytest.mark.asyncio
async def test_algo_decision_over_tier_lot_size_rejected():
    algo_config_state.configure(
        mode="MANUAL", underlying="NIFTY", capital=1000000.0, lot_schedule=[2, 3],
    )
    algo_config_state.enable()

    engine = RiskEngine(GENEROUS_LIMITS)
    # tier 1 allows 2 lots = 130 qty; requesting 3 lots = 195
    published = await _run(engine, _decision(quantity=195))

    assert "EXECUTION_REQUEST" not in [t for t, _ in published]
    risk_decision = next(p for t, p in published if t == "RISK_DECISION")
    assert "Tier 1 allows at most 2 lots" in risk_decision["reason"]


@pytest.mark.asyncio
async def test_manual_trading_decision_bypasses_algo_gate_even_when_disabled():
    # algo trading stays disabled (default from the fixture) — a manual
    # trading order must be completely unaffected by that.
    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision(source="MANUAL_TRADING"))

    assert "EXECUTION_REQUEST" in [t for t, _ in published]


@pytest.mark.asyncio
async def test_manual_trading_decision_ignores_algo_capital_budget():
    algo_config_state.configure(
        mode="MANUAL", underlying="NIFTY", capital=1.0, lot_schedule=[1],  # tiny budget
    )
    algo_config_state.enable()

    engine = RiskEngine(GENEROUS_LIMITS)
    published = await _run(engine, _decision(source="MANUAL_TRADING", quantity=130, price=100.0))

    # A manual order for the same underlying, way over the algo budget,
    # must still pass — that budget is for the algo, not manual trading.
    assert "EXECUTION_REQUEST" in [t for t, _ in published]


# --------------------------- record_execution ---------------------------

@pytest.mark.asyncio
async def test_record_execution_updates_capital_only_on_submitted_for_algo():
    engine = RiskEngine(GENEROUS_LIMITS)
    await engine.record_execution({
        "status": "DRY_RUN", "source": "ALGO", "quantity": 130, "price": 100.0,
        "instrument_token": "NSE_FO|1",
    })
    assert engine.state.capital_deployed_today == 0.0  # DRY_RUN doesn't spend real capital

    await engine.record_execution({
        "status": "SUBMITTED", "source": "ALGO", "quantity": 130, "price": 100.0,
        "instrument_token": "NSE_FO|1",
    })
    assert engine.state.capital_deployed_today == pytest.approx(13000.0)


@pytest.mark.asyncio
async def test_record_execution_advances_fill_count_on_dry_run_and_submitted_for_algo():
    engine = RiskEngine(GENEROUS_LIMITS)
    await engine.record_execution({
        "status": "DRY_RUN", "source": "ALGO", "quantity": 130, "price": 100.0,
        "instrument_token": "NSE_FO|1",
    })
    assert engine.state.fill_count_by_instrument["NSE_FO|1"] == 1

    await engine.record_execution({
        "status": "SUBMITTED", "source": "ALGO", "quantity": 130, "price": 100.0,
        "instrument_token": "NSE_FO|1",
    })
    assert engine.state.fill_count_by_instrument["NSE_FO|1"] == 2


@pytest.mark.asyncio
async def test_record_execution_ignores_non_algo_source_for_capital_and_fill_count():
    engine = RiskEngine(GENEROUS_LIMITS)
    await engine.record_execution({
        "status": "SUBMITTED", "source": "MANUAL_TRADING", "quantity": 130, "price": 100.0,
        "instrument_token": "NSE_FO|1",
    })
    assert engine.state.capital_deployed_today == 0.0
    assert engine.state.fill_count_by_instrument == {}
    # But the universal daily order counter still applies to everyone.
    assert engine.state.orders_placed_today == 1


@pytest.mark.asyncio
async def test_record_execution_never_counts_rejected_or_error_for_fill_count():
    engine = RiskEngine(GENEROUS_LIMITS)
    await engine.record_execution({
        "status": "REJECTED", "source": "ALGO", "quantity": 130, "price": 100.0,
        "instrument_token": "NSE_FO|1",
    })
    await engine.record_execution({
        "status": "ERROR", "source": "ALGO", "quantity": 130, "price": 100.0,
        "instrument_token": "NSE_FO|1",
    })
    assert engine.state.fill_count_by_instrument == {}
    assert engine.state.capital_deployed_today == 0.0
