import pytest
import asyncio
from datetime import datetime, timezone
from backend.app.strategies.pullback_chop_filter.engine import PullbackChopFilterStrategy
from backend.app.market_data.models import Tick, Candle

@pytest.fixture
def strategy():
    return PullbackChopFilterStrategy()

@pytest.mark.asyncio
async def test_chop_zone_bands(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)

    # Init Supertrend and VWAP to mock bands
    state["last_vwap"] = 100.0
    state["current_st"] = 110.0

    # Tick inside bands, should trigger CHOP_ZONE
    await strategy._evaluate_state(instrument, state, 105.0)
    assert state["market_state"] == "CHOP_ZONE"
    assert state["internal_state"] == "WAITING"
    assert state["active_signal"]["type"] == "WAIT"

@pytest.mark.asyncio
async def test_chop_zone_oi_conviction(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)

    state["last_vwap"] = 100.0
    state["current_st"] = 90.0
    # Price outside band
    ltp = 105.0

    # Low Conviction
    state["oi_diff_pct"] = 35.0
    await strategy._evaluate_state(instrument, state, ltp)
    assert state["market_state"] == "CHOP_ZONE"

@pytest.mark.asyncio
async def test_bullish_trend_confirmation_and_tiers(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)

    state["last_vwap"] = 100.0
    state["current_st"] = 90.0
    state["oi_diff_pct"] = 45.0

    # 1. Breakout -> Trend confirmed
    await strategy._evaluate_state(instrument, state, 105.0)
    assert state["market_state"] == "TRENDING_BULLISH"
    assert state["internal_state"] == "BULLISH_TREND_CONFIRMED"

    # 2. Pullback to SuperTrend (Tier 1)
    await strategy._evaluate_state(instrument, state, 90.0)
    assert state["internal_state"] == "BULLISH_TIER_1"
    assert state["active_signal"]["type"] == "BUY_TIER_1"

    # 3. Pullback to VWAP (Tier 2)
    # Using 100.0 (exact touch)
    await strategy._evaluate_state(instrument, state, 100.0)
    assert state["internal_state"] == "BULLISH_TIER_2"
    assert state["active_signal"]["type"] == "BUY_TIER_2"

@pytest.mark.asyncio
async def test_bearish_trend_and_invalidation(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)

    state["last_vwap"] = 100.0
    state["current_st"] = 110.0
    state["oi_diff_pct"] = -50.0

    # 1. Breakdown -> Trend confirmed
    await strategy._evaluate_state(instrument, state, 90.0)
    assert state["market_state"] == "TRENDING_BEARISH"
    assert state["internal_state"] == "BEARISH_TREND_CONFIRMED"

    # 2. Invalidate on candle close
    candle = Candle(
        instrument=instrument,
        timeframe="3m",
        timestamp=datetime.now(timezone.utc),
        open=95.0,
        high=102.0,
        low=90.0,
        close=101.0, # Closes above VWAP (100.0)
        volume=100,
        is_closed=True
    )
    await strategy._check_invalidation(candle, state)
    assert state["market_state"] == "CHOP_ZONE"
    assert state["internal_state"] == "INVALIDATED"
    assert state["active_signal"]["type"] == "STOP_LOSS_HIT"
