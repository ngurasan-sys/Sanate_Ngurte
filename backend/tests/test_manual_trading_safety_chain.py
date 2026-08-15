"""Proves a manual order is not a separate, faster path to the broker: it
must pass through the exact same RiskEngine and ExecutionEngine every
automated strategy uses, and that the resulting position status reflects
what the risk/execution pipeline actually decided — not what was merely
attempted. Same "chain the real engines together" style as
test_signal_to_decision_chain.py / test_risk_execution_chain.py.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.engines.execution import ExecutionEngine
from backend.app.engines.risk import RiskEngine
from backend.app.execution.risk_limits import RiskLimits
from backend.app.strategies.manual_trading.engine import ManualTradingEngine
from backend.app.strategies.manual_trading.models import ManualOrderRequest


def _row(strike, call_ltp=100.0):
    # instrument_key is a sibling of market_data in the real Upstox
    # response (verified live), not nested inside it.
    return {
        "strike_price": strike,
        "underlying_spot_price": 24500.0,
        "call_options": {"instrument_key": "CE1", "market_data": {"ltp": call_ltp}},
        "put_options": {"instrument_key": "PE1", "market_data": {"ltp": 90.0}},
    }


CHAIN = [_row(24500)]

PATCH_TOKEN = "backend.app.strategies.manual_trading.engine.upstox_auth.load_token"
PATCH_FETCH = "backend.app.strategies.manual_trading.engine.fetch_option_chain"


async def _place_order_through_full_chain(risk_limits: RiskLimits, lots: int = 1):
    """Chains ManualTradingEngine -> RiskEngine -> ExecutionEngine ->
    back into ManualTradingEngine's own RISK_DECISION/EXECUTION_UPDATE
    handlers, exactly as the real event bus would route it — proving the
    position's final status comes from what the pipeline actually decided.
    """
    manual_engine = ManualTradingEngine()
    risk_engine = RiskEngine(risk_limits)
    execution_engine = ExecutionEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))
        if topic == "DECISION_CREATED":
            await risk_engine.process_decision(payload)
        elif topic == "RISK_DECISION":
            await manual_engine._on_risk_decision(payload)
        elif topic == "EXECUTION_REQUEST":
            await execution_engine.execute_order(payload)
        elif topic == "EXECUTION_UPDATE":
            await manual_engine._on_execution_update(payload)

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch("backend.app.strategies.manual_trading.engine.event_bus.publish", new=capture), \
         patch("backend.app.engines.risk.event_bus.publish", new=capture), \
         patch("backend.app.engines.execution.event_bus.publish", new=capture), \
         patch("backend.app.engines.risk.datetime") as mock_dt:
        # In-session time so the market-hours check passes regardless of
        # when the suite actually runs, same as test_risk_execution_chain.py.
        mock_dt.now.return_value = datetime(2026, 1, 1, 11, 0)
        position = await manual_engine.place_order(ManualOrderRequest(
            underlying="NIFTY", option_type="CE", strike=24500.0,
            lots=lots, stop_loss=50.0, target=150.0, pyramid_lot_size=0,
        ))

    return manual_engine, position, published


@pytest.mark.asyncio
async def test_manual_order_within_limits_reaches_dry_run_execution(monkeypatch):
    monkeypatch.delenv("UPSTOX_EXECUTION_MODE", raising=False)
    manual_engine, position, published = await _place_order_through_full_chain(RiskLimits(), lots=1)
    topics = [t for t, _ in published]

    assert "RISK_DECISION" in topics
    assert "EXECUTION_REQUEST" in topics
    assert "EXECUTION_UPDATE" in topics

    exec_update = next(p for t, p in published if t == "EXECUTION_UPDATE")
    # Default env: no UPSTOX_EXECUTION_MODE=LIVE, no arm switch -> DRY_RUN,
    # never a real broker submission, no matter how the manual order was placed.
    assert exec_update["status"] == "DRY_RUN"
    assert exec_update["order_id"] is None

    # And critically: the position itself reflects that confirmed outcome.
    assert manual_engine.positions[position.position_id].status == "OPEN"


@pytest.mark.asyncio
async def test_manual_order_exceeding_quantity_limit_is_rejected_by_risk():
    # NIFTY lot size 65; 1 lot = 65 units. Cap it below that so risk rejects it.
    manual_engine, position, published = await _place_order_through_full_chain(
        RiskLimits(max_quantity_per_order=50), lots=1,
    )
    topics = [t for t, _ in published]

    assert "RISK_DECISION" in topics
    assert "EXECUTION_REQUEST" not in topics

    risk_decision = next(p for t, p in published if t == "RISK_DECISION")
    assert risk_decision["approved"] is False
    assert "exceeds max_quantity_per_order" in risk_decision["reason"]

    # The exact live-observed bug this fixes: a risk-rejected order must
    # never leave a phantom OPEN position behind.
    final = manual_engine.positions[position.position_id]
    assert final.status == "CLOSED"
    assert "exceeds max_quantity_per_order" in final.exit_reason


@pytest.mark.asyncio
async def test_manual_order_blocked_while_risk_engine_halted():
    manual_engine = ManualTradingEngine()
    risk_engine = RiskEngine()
    risk_engine.halt("kill switch test")
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))
        if topic == "DECISION_CREATED":
            await risk_engine.process_decision(payload)
        elif topic == "RISK_DECISION":
            await manual_engine._on_risk_decision(payload)

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch("backend.app.strategies.manual_trading.engine.event_bus.publish", new=capture), \
         patch("backend.app.engines.risk.event_bus.publish", new=capture):
        position = await manual_engine.place_order(ManualOrderRequest(
            underlying="NIFTY", option_type="CE", strike=24500.0,
            lots=1, stop_loss=50.0, target=150.0, pyramid_lot_size=0,
        ))

    topics = [t for t, _ in published]
    assert "EXECUTION_REQUEST" not in topics
    risk_decision = next(p for t, p in published if t == "RISK_DECISION")
    assert risk_decision["approved"] is False
    assert "kill switch test" in risk_decision["reason"]

    final = manual_engine.positions[position.position_id]
    assert final.status == "CLOSED"
    assert "kill switch test" in final.exit_reason
