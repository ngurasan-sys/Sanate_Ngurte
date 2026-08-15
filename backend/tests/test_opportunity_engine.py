"""Tests for OpportunityEngine, the STRATEGY_SIGNAL -> OPPORTUNITY_CREATED
bridge. Style mirrors test_risk_execution_chain.py: patch event_bus.publish
and inspect what actually got published, rather than asserting on internals.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from backend.app.engines.opportunity import OpportunityEngine, _infer_direction


def _compatible_signal(**kw):
    """Shape used by trending_oi_price_action, level_based, and oh_ol —
    the three strategies that already match OpportunityEngine's contract.
    """
    d = {
        "signal_id": "SIG_1",
        "strategy_id": "trending_oi_pa",
        "instrument": "NIFTY 24500 CE",
        "timestamp": datetime(2026, 1, 1, 11, 0),
        "direction": "CALL",
        "confidence": 85.0,
        "evidence": "test",
    }
    d.update(kw)
    return d


def _gap_opening_style_signal(**kw):
    """Shape actually used by gap_opening/atr: symbol/underlying + action,
    no instrument, no direction, no confidence field at all.
    """
    d = {
        "signal_id": "GAP_1",
        "strategy_id": "gap_opening_strategies",
        "strategy_name": "Gap Opening Strategies",
        "symbol": "NIFTY",
        "underlying": "NIFTY",
        "action": "BUY_CE",
        "timestamp": datetime(2026, 1, 1, 11, 0),
    }
    d.update(kw)
    return d


@pytest.mark.asyncio
async def test_compatible_signal_creates_and_publishes_opportunity():
    engine = OpportunityEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    with patch("backend.app.engines.opportunity.event_bus.publish", new=capture):
        await engine.process_signal(_compatible_signal())

    assert len(engine.opportunities) == 1
    assert published[0][0] == "OPPORTUNITY_CREATED"
    payload = published[0][1]
    assert payload["opportunity_id"] == "OPP_SIG_1"
    assert payload["instrument"] == "NIFTY 24500 CE"
    assert payload["direction"] == "CALL"
    assert payload["confidence"] == 85.0
    assert payload["source_signals"] == ["SIG_1"]


@pytest.mark.asyncio
async def test_gap_opening_style_signal_is_dropped_not_crashed():
    """The whole point of this fix: a strategy with no confidence field
    must not crash the subscriber and must not fabricate a confidence
    value — it should be dropped, loudly logged, and nothing else."""
    engine = OpportunityEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    with patch("backend.app.engines.opportunity.event_bus.publish", new=capture):
        await engine.process_signal(_gap_opening_style_signal())  # must not raise

    assert published == []
    assert engine.opportunities == []


@pytest.mark.asyncio
async def test_signal_missing_confidence_but_with_direction_is_still_dropped():
    engine = OpportunityEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    signal = _compatible_signal()
    del signal["confidence"]

    with patch("backend.app.engines.opportunity.event_bus.publish", new=capture):
        await engine.process_signal(signal)

    assert published == []


def test_infer_direction_prefers_explicit_direction_field():
    assert _infer_direction({"direction": "PUT", "action": "BUY_CE"}) == "PUT"


def test_infer_direction_derives_from_ce_pe_action():
    assert _infer_direction({"action": "BUY_CE"}) == "CALL"
    assert _infer_direction({"action": "BUY_PE"}) == "PUT"


def test_infer_direction_none_when_unrecoverable():
    assert _infer_direction({"action": "TRAIL_SL"}) is None
    assert _infer_direction({}) is None


@pytest.mark.asyncio
async def test_action_derived_direction_lets_a_signal_through_when_confidence_present():
    """If a gap_opening-shaped signal DID carry a confidence and an
    instrument (hypothetically), direction should still be recoverable
    from the CE/PE action rather than requiring an explicit field.
    """
    engine = OpportunityEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    signal = _gap_opening_style_signal(instrument="NIFTY 24500 CE", confidence=90.0)

    with patch("backend.app.engines.opportunity.event_bus.publish", new=capture):
        await engine.process_signal(signal)

    assert published[0][1]["direction"] == "CALL"


@pytest.mark.asyncio
async def test_opportunities_list_capped_at_1000():
    engine = OpportunityEngine()
    engine.opportunities = [None] * 1000  # type: ignore[list-item]

    async def capture(topic, payload):
        pass

    with patch("backend.app.engines.opportunity.event_bus.publish", new=capture):
        await engine.process_signal(_compatible_signal(signal_id="SIG_NEW"))

    assert len(engine.opportunities) == 1000
    assert engine.opportunities[-1].opportunity_id == "OPP_SIG_NEW"
