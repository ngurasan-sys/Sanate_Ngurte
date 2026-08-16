import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.app.order_flow.footprint_processor import FootprintProcessor, TRACKED_TIMEFRAMES


@pytest.mark.asyncio
async def test_on_tick_updates_every_tracked_timeframe():
    processor = FootprintProcessor()
    tick = {
        "instrument_key": "NIFTY FUT", "price": 24500.0, "volume": 100,
        "direction": "AGGRESSIVE_BUY", "timestamp": datetime.now(timezone.utc),
    }
    await processor._on_tick(tick)

    for timeframe in TRACKED_TIMEFRAMES:
        candle = processor.aggregator.get_current("NIFTY FUT", timeframe)
        assert candle is not None
        assert candle.close == 24500.0

    assert "NIFTY FUT" in processor._dirty_instruments


@pytest.mark.asyncio
async def test_broadcast_publishes_candles_for_dirty_instruments_only():
    processor = FootprintProcessor(broadcast_interval_seconds=0.01)
    tick = {
        "instrument_key": "NIFTY FUT", "price": 24500.0, "volume": 100,
        "direction": "AGGRESSIVE_BUY", "timestamp": datetime.now(timezone.utc),
    }
    await processor._on_tick(tick)

    published = []

    async def _fake_publish(channel, payload):
        published.append((channel, payload))

    with patch("backend.app.order_flow.footprint_processor.event_bus.publish", side_effect=_fake_publish):
        processor.running = True
        loop_task = asyncio.create_task(processor._broadcast_loop())
        for _ in range(20):
            if published:
                break
            await asyncio.sleep(0.02)
        processor.running = False
        loop_task.cancel()

    assert published
    channel, payload = published[0]
    assert channel == "footprint_candles"
    assert payload["instrument_key"] == "NIFTY FUT"
    assert set(payload["candles"].keys()) == set(TRACKED_TIMEFRAMES)
    assert not processor._dirty_instruments  # cleared after broadcast


@pytest.mark.asyncio
async def test_broadcast_skips_publish_when_nothing_changed():
    processor = FootprintProcessor(broadcast_interval_seconds=0.01)

    published = []

    async def _fake_publish(channel, payload):
        published.append((channel, payload))

    with patch("backend.app.order_flow.footprint_processor.event_bus.publish", side_effect=_fake_publish):
        processor.running = True
        loop_task = asyncio.create_task(processor._broadcast_loop())
        await asyncio.sleep(0.05)
        processor.running = False
        loop_task.cancel()

    assert published == []


def test_set_imbalance_ratio_pct_updates_the_shared_aggregator():
    processor = FootprintProcessor()
    processor.set_imbalance_ratio_pct(450.0)
    assert processor.aggregator.imbalance_ratio_pct == 450.0
