import pytest
from datetime import datetime, timezone
from app.strategies.gap_opening.gap_opening_strategies import GapOpeningStrategies, GapDirection
from app.market_data.models import Tick

@pytest.mark.asyncio
async def test_gap_opening_0945_guard():
    strategy = GapOpeningStrategies()

    tick = {"instrument": "NIFTY", "price": 100.0, "timestamp": "2023-01-01T09:14:00Z"}
    await strategy.evaluate(tick)
    assert strategy.market_phase == "WAITING"

    tick = {"instrument": "NIFTY", "price": 100.0, "timestamp": "2023-01-01T09:30:00Z"}
    await strategy.evaluate(tick)
    assert strategy.market_phase == "OPENING DISCOVERY"

    tick = {"instrument": "NIFTY", "price": 100.0, "timestamp": "2023-01-01T09:44:59Z"}
    await strategy.evaluate(tick)
    assert strategy.market_phase == "OPENING DISCOVERY"

    tick = {"instrument": "NIFTY", "price": 100.0, "timestamp": "2023-01-01T09:45:00Z"}
    await strategy.evaluate(tick)
    assert strategy.market_phase == "DISCOVERY COMPLETE"

@pytest.mark.asyncio
async def test_gap_opening_gap_classification():
    strategy = GapOpeningStrategies()

    strategy._update_gap_stats(100.0, 102.0)
    assert strategy.gap_direction == GapDirection.GAP_UP

    strategy._update_gap_stats(100.0, 98.0)
    assert strategy.gap_direction == GapDirection.GAP_DOWN

    strategy._update_gap_stats(100.0, 100.05)
    assert strategy.gap_direction == GapDirection.FLAT

@pytest.mark.asyncio
async def test_gap_opening_atr_exhaustion():
    strategy = GapOpeningStrategies()

    tick = {"instrument": "NIFTY", "price": 100.0, "timestamp": "2023-01-01T09:45:00Z"}
    context = {"daily_atr": 100.0, "day_high": 200.0, "day_low": 100.0}

    await strategy.evaluate(tick, context)
    assert strategy.market_phase == "EXHAUSTED"

@pytest.mark.asyncio
async def test_gap_opening_bullish_entry():
    strategy = GapOpeningStrategies()

    tick = {"instrument": "NIFTY", "price": 105.0, "timestamp": "2023-01-01T09:46:00Z"}
    context = {
        "daily_atr": 100.0,
        "day_high": 110.0,
        "day_low": 100.0,
        "trending_oi_percent": 45.0,
        "supertrend": 100.0,
        "vwap": 102.0
    }

    emitted = []
    async def mock_emit(instrument, direction, confidence, evidence):
        emitted.append({"dir": direction})
    strategy.emit_signal = mock_emit

    await strategy.evaluate(tick, context)
    assert len(emitted) == 1
    assert emitted[0]["dir"] == "BUY_CE"
    assert strategy.tier_1_status == "TRIGGERED"
    assert strategy.market_phase == "IN POSITION"

@pytest.mark.asyncio
async def test_gap_opening_bearish_entry():
    strategy = GapOpeningStrategies()

    tick = {"instrument": "NIFTY", "price": 95.0, "timestamp": "2023-01-01T09:46:00Z"}
    context = {
        "daily_atr": 100.0,
        "day_high": 110.0,
        "day_low": 90.0,
        "trending_oi_percent": -45.0,
        "supertrend": 100.0,
        "vwap": 98.0
    }

    emitted = []
    async def mock_emit(instrument, direction, confidence, evidence):
        emitted.append({"dir": direction})
    strategy.emit_signal = mock_emit

    await strategy.evaluate(tick, context)
    assert len(emitted) == 1
    assert emitted[0]["dir"] == "BUY_PE"
    assert strategy.tier_1_status == "TRIGGERED"
    assert strategy.market_phase == "IN POSITION"
