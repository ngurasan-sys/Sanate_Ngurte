from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.app.order_flow.footprint_candle import FootprintCandle
from backend.app.order_flow.models import FootprintNode
from backend.app.strategies.order_flow_absorption.config import OFAOConfig
from backend.app.strategies.order_flow_absorption.engine import OFAOEngine

BASE = datetime(2024, 10, 1, 6, 0, tzinfo=timezone.utc)
INSTRUMENT = "NIFTY FUT"


def _candle():
    return FootprintCandle(
        instrument_key=INSTRUMENT, timeframe="5m", open_time=BASE,
        open=100, high=101, low=99, close=100.5, footprint={100.5: FootprintNode(price=100.5, bid_volume=1, ask_volume=1)},
    )


@pytest.mark.asyncio
async def test_update_snapshot_always_broadcasts_ofao_state():
    engine = OFAOEngine(config=OFAOConfig())
    published = []

    async def _fake_publish(channel, payload):
        published.append((channel, payload))

    with patch("backend.app.strategies.order_flow_absorption.engine.event_bus.publish", side_effect=_fake_publish):
        await engine._update_snapshot(INSTRUMENT, "NIFTY", [_candle()], BASE)

    channels = [c for c, _ in published]
    assert "ofao_state" in channels


@pytest.mark.asyncio
async def test_update_snapshot_persists_only_on_first_call_state_change():
    engine = OFAOEngine(config=OFAOConfig())
    published = []

    async def _fake_publish(channel, payload):
        published.append((channel, payload))

    with patch("backend.app.strategies.order_flow_absorption.engine.event_bus.publish", side_effect=_fake_publish):
        await engine._update_snapshot(INSTRUMENT, "NIFTY", [_candle()], BASE)
        first_persist_count = sum(1 for c, _ in published if c == "persist_ofao_setup")

        # Second call, same state (NO_SETUP) — must not persist again.
        await engine._update_snapshot(INSTRUMENT, "NIFTY", [_candle()], BASE)
        second_persist_count = sum(1 for c, _ in published if c == "persist_ofao_setup")

    assert first_persist_count == 1
    assert second_persist_count == 1  # unchanged — no new persist row


def test_get_snapshot_returns_none_before_any_evaluation():
    engine = OFAOEngine(config=OFAOConfig())
    assert engine.get_snapshot(INSTRUMENT) is None


@pytest.mark.asyncio
async def test_get_snapshot_returns_latest_after_update():
    engine = OFAOEngine(config=OFAOConfig())
    with patch("backend.app.strategies.order_flow_absorption.engine.event_bus.publish"):
        await engine._update_snapshot(INSTRUMENT, "NIFTY", [_candle()], BASE)
    snapshot = engine.get_snapshot(INSTRUMENT)
    assert snapshot is not None
    assert snapshot["instrument_key"] == INSTRUMENT
    assert snapshot["state"] == "NO_SETUP"
    assert snapshot["last_price"] == 100.5
