"""Proves the STRATEGY_SIGNAL -> OpportunityEngine -> DecisionEngine chain
actually connects now that opportunity_engine is started in main.py's
lifespan (previously it was never started, so no strategy signal reached
decision/risk/execution regardless of DRY_RUN/LIVE mode). Chains the real
OpportunityEngine and DecisionEngine together, same "verify the wiring,
not each piece in isolation" style as test_risk_execution_chain.py.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from backend.app.engines.decision import DecisionEngine
from backend.app.engines.opportunity import OpportunityEngine


async def _run_signal_through_opportunity_and_decision(signal):
    """Wires OpportunityEngine's process_signal directly into
    DecisionEngine's process_opportunity, capturing every publish along
    the way — the same in-process chaining event_bus does at runtime,
    without needing the event bus itself running.
    """
    opportunity_engine = OpportunityEngine()
    decision_engine = DecisionEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))
        if topic == "OPPORTUNITY_CREATED":
            await decision_engine.process_opportunity(payload)

    with patch("backend.app.engines.opportunity.event_bus.publish", new=capture), \
         patch("backend.app.engines.decision.event_bus.publish", new=capture):
        await opportunity_engine.process_signal(signal)

    return published


@pytest.mark.asyncio
async def test_high_confidence_signal_flows_through_to_a_trade_decision():
    signal = {
        "signal_id": "SIG_1",
        "strategy_id": "trending_oi_pa",
        "instrument": "NIFTY 24500 CE",
        "timestamp": datetime(2026, 1, 1, 11, 0),
        "direction": "CALL",
        "confidence": 85.0,
    }

    published = await _run_signal_through_opportunity_and_decision(signal)
    topics = [t for t, _ in published]

    assert "OPPORTUNITY_CREATED" in topics
    assert "DECISION_CREATED" in topics
    decision = next(p for t, p in published if t == "DECISION_CREATED")
    assert decision["action"] == "TRADE"
    assert decision["instrument"] == "NIFTY 24500 CE"


@pytest.mark.asyncio
async def test_low_confidence_signal_flows_through_to_a_wait_decision():
    signal = {
        "signal_id": "SIG_2",
        "strategy_id": "trending_oi_pa",
        "instrument": "NIFTY 24500 PE",
        "timestamp": datetime(2026, 1, 1, 11, 0),
        "direction": "PUT",
        "confidence": 60.0,
    }

    published = await _run_signal_through_opportunity_and_decision(signal)
    decision = next(p for t, p in published if t == "DECISION_CREATED")
    assert decision["action"] == "WAIT"


@pytest.mark.asyncio
async def test_gap_opening_style_signal_never_reaches_a_decision():
    """The known limitation, verified explicitly: a strategy whose signal
    has no confidence field produces no Opportunity, so DecisionEngine
    never even runs for it — not a WAIT, not a TRADE, nothing.
    """
    signal = {
        "signal_id": "GAP_1",
        "strategy_id": "gap_opening_strategies",
        "symbol": "NIFTY",
        "underlying": "NIFTY",
        "action": "BUY_CE",
        "timestamp": datetime(2026, 1, 1, 11, 0),
    }

    published = await _run_signal_through_opportunity_and_decision(signal)
    assert published == []
