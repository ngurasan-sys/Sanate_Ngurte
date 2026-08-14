import pytest
import asyncio
from datetime import datetime, timedelta
import pytz

from app.strategies.atr.atr_strategies_engine import ATRStrategiesEngine
from app.market_data.models import Tick, Candle
from app.core.event_bus import event_bus

@pytest.fixture
def engine():
    eng = ATRStrategiesEngine()
    eng.start()
    yield eng
    eng.stop()

@pytest.fixture
def tz():
    return pytz.timezone('Asia/Kolkata')

@pytest.mark.asyncio
async def test_strategy_registration(engine):
    assert engine.strategy_id == "atr_strategies"
    assert engine.strategy_name == "ATR Strategies"

@pytest.mark.asyncio
async def test_time_gates(engine, tz):
    now = datetime.now(tz)

    # Discovery (09:15-09:45)
    dt_discovery = now.replace(hour=9, minute=30, second=0)
    engine._update_session_state("NIFTY", dt_discovery)
    state = engine._get_underlying_state("NIFTY")
    assert state["state"] == "DISCOVERY"

    # Active (09:45-14:00)
    dt_active = now.replace(hour=10, minute=0, second=0)
    engine._update_session_state("NIFTY", dt_active)
    state = engine._get_underlying_state("NIFTY")
    assert state["state"] == "ACTIVE"

    # Late Session (>=14:00)
    dt_late = now.replace(hour=14, minute=5, second=0)
    engine._update_session_state("NIFTY", dt_late)
    state = engine._get_underlying_state("NIFTY")
    assert state["state"] == "LATE_SESSION"

@pytest.mark.asyncio
async def test_trending_oi_bullish(engine):
    await engine.on_trending_oi({
        "type": "tick_update", "view": "spot_trending_oi", "underlying": "NIFTY",
        "row": {"directionPercent": 42.0, "differenceOi": 1000, "changeCeOi": -100, "changePeOi": 1100}
    })
    state = engine._get_underlying_state("NIFTY")
    assert state["trending_oi_bullish"] is True
    assert state["trending_oi_bearish"] is False
    assert state["trending_oi_reason"] == "TRENDING_OI"

@pytest.mark.asyncio
async def test_trending_oi_short_covering(engine):
    await engine.on_trending_oi({
        "type": "tick_update", "view": "spot_trending_oi", "underlying": "NIFTY",
        "row": {"directionPercent": 20.0, "differenceOi": 1000, "changeCeOi": -500, "changePeOi": 1500}
    })
    state = engine._get_underlying_state("NIFTY")
    assert state["trending_oi_bullish"] is True
    assert state["trending_oi_reason"] == "CALL_OI_SHORT_COVERING"

@pytest.mark.asyncio
async def test_trending_oi_bearish(engine):
    await engine.on_trending_oi({
        "type": "tick_update", "view": "spot_trending_oi", "underlying": "NIFTY",
        "row": {"directionPercent": -45.0, "differenceOi": -1000, "changeCeOi": 1100, "changePeOi": 100}
    })
    state = engine._get_underlying_state("NIFTY")
    assert state["trending_oi_bullish"] is False
    assert state["trending_oi_bearish"] is True

@pytest.mark.asyncio
async def test_futures_confirmation_volume(engine, tz):
    now = datetime.now(tz)
    state = engine._get_underlying_state("NIFTY")
    state["futures_volume_history"] = [1000] * 20
    wma = engine._get_volume_wma(state)
    assert wma == 1000.0

    candle = Candle(instrument="NIFTY_FUT", timeframe="3m", timestamp=now, open=100, high=105, low=95, close=102, volume=1501)
    vol_spike = candle.volume >= (1.5 * wma)
    assert vol_spike is True

    candle_low = Candle(instrument="NIFTY_FUT", timeframe="3m", timestamp=now, open=100, high=105, low=95, close=102, volume=1200)
    vol_spike_low = candle_low.volume >= (1.5 * wma)
    assert vol_spike_low is False

@pytest.mark.asyncio
async def test_atr_exhaustion(engine):
    state = engine._get_underlying_state("NIFTY")
    state["daily_atr"] = 100.0

    # Not exhausted
    state["day_high"] = 25050.0
    state["day_low"] = 25000.0 # Range = 50
    assert engine._is_atr_exhausted(state) is False

    # Exhausted
    state["day_high"] = 25150.0
    state["day_low"] = 25000.0 # Range = 150
    assert engine._is_atr_exhausted(state) is True

@pytest.mark.asyncio
async def test_tier_1_entry(engine, tz):
    now = datetime.now(tz).replace(hour=10, minute=0, second=0)
    state = engine._get_underlying_state("NIFTY")

    # Setup valid conditions
    state["state"] = "ACTIVE"
    state["trending_oi_bullish"] = True
    state["supertrend"] = 24990.0
    state["supertrend_direction"] = 1
    state["daily_atr"] = 100.0
    state["day_high"] = 25050.0
    state["day_low"] = 25000.0
    state["futures_oi_change"] = -500
    state["futures_volume_history"] = [1000] * 20

    candle = Candle(instrument="NIFTY_FUT", timeframe="3m", timestamp=now, open=25000.0, high=25020.0, low=24992.0, close=25010.0, volume=2000)

    await engine._evaluate_entries("NIFTY", candle)

    pos = state["position"]
    assert pos["active"] is True
    assert pos["direction"] == "BUY_CE"
    assert pos["tier_1_filled"] is True
    assert pos["tier_2_filled"] is False
    assert pos["lots_held"] == 2
    assert pos["avg_entry_price"] == 25010.0
    assert pos["current_sl"] == 24992.0 - 10.0 # low - trailing buffer

@pytest.mark.asyncio
async def test_tier_1_entry_bearish(engine, tz):
    now = datetime.now(tz).replace(hour=10, minute=0, second=0)
    state = engine._get_underlying_state("BANKNIFTY")

    # Setup valid conditions for bearish
    state["state"] = "ACTIVE"
    state["trending_oi_bearish"] = True
    state["supertrend"] = 45010.0
    state["supertrend_direction"] = -1
    state["daily_atr"] = 100.0
    state["day_high"] = 45050.0
    state["day_low"] = 45000.0
    state["futures_oi_change"] = -500
    state["futures_volume_history"] = [1000] * 20

    # Bearish pullback: high >= supertrend - tolerance, close <= supertrend, vol spike, close < open
    candle = Candle(instrument="BANKNIFTY_FUT", timeframe="3m", timestamp=now, open=45005.0, high=45008.0, low=44990.0, close=44995.0, volume=2000)

    await engine._evaluate_entries("BANKNIFTY", candle)

    pos = state["position"]
    assert pos["active"] is True
    assert pos["direction"] == "BUY_PE"
    assert pos["tier_1_filled"] is True
    assert pos["tier_2_filled"] is False
    assert pos["lots_held"] == 2
    assert pos["avg_entry_price"] == 44995.0
    assert pos["current_sl"] == 45008.0 + 10.0

@pytest.mark.asyncio
async def test_tier_2_entry(engine, tz):
    now = datetime.now(tz)
    state = engine._get_underlying_state("NIFTY")

    pos = state["position"]
    pos["active"] = True
    pos["direction"] = "BUY_CE"
    pos["tier_1_filled"] = True
    pos["tier_2_filled"] = False
    pos["lots_held"] = 2
    pos["avg_entry_price"] = 100.0

    state["vwap"] = 90.0

    # Tick dips into VWAP buffer
    tick = Tick(instrument="NIFTY_FUT", price=95.0, timestamp=now)
    await engine._evaluate_position("NIFTY", tick)

    assert pos["tier_2_filled"] is True
    assert pos["lots_held"] == 6

@pytest.mark.asyncio
async def test_weighted_average_entry(engine, tz):
    now = datetime.now(tz)
    state = engine._get_underlying_state("NIFTY")
    pos = state["position"]
    pos["active"] = True
    pos["direction"] = "BUY_CE"
    pos["tier_1_filled"] = True
    pos["tier_2_filled"] = False
    pos["lots_held"] = 2
    pos["avg_entry_price"] = 100.0

    state["vwap"] = 90.0

    tick = Tick(instrument="NIFTY_FUT", price=90.0, timestamp=now)
    await engine._evaluate_position("NIFTY", tick)

    assert pos["lots_held"] == 6
    expected_avg = ((2 * 100.0) + (4 * 90.0)) / 6
    assert pos["avg_entry_price"] == expected_avg

@pytest.mark.asyncio
async def test_vwap_hard_invalidation(engine, tz):
    now = datetime.now(tz)
    state = engine._get_underlying_state("NIFTY")
    pos = state["position"]
    pos["active"] = True
    pos["direction"] = "BUY_CE"
    pos["lots_held"] = 2

    state["vwap"] = 100.0

    # Price closes below VWAP - 8
    tick = Tick(instrument="NIFTY_FUT", price=90.0, timestamp=now)
    tick.is_trade = True # Need to set is_trade to ensure it gets picked up if filtered
    await engine._evaluate_position("NIFTY", tick)

    assert pos["active"] is False
    assert pos["lots_held"] == 0

@pytest.mark.asyncio
async def test_partial_profit_and_break_even(engine, tz):
    now = datetime.now(tz)
    state = engine._get_underlying_state("NIFTY")
    pos = state["position"]
    pos["active"] = True
    pos["direction"] = "BUY_CE"
    pos["lots_held"] = 6
    pos["avg_entry_price"] = 100.0
    pos["current_sl"] = 80.0

    # Target is avg + 20 = 120
    tick = Tick(instrument="NIFTY_FUT", price=125.0, timestamp=now)
    await engine._evaluate_position("NIFTY", tick)

    assert pos["partial_booked"] is True
    assert pos["lots_held"] == 4
    assert pos["current_sl"] == 100.0 # Break-even

@pytest.mark.asyncio
async def test_trailing_stop(engine, tz):
    now = datetime.now(tz)
    state = engine._get_underlying_state("NIFTY")
    pos = state["position"]
    pos["active"] = True
    pos["direction"] = "BUY_CE"
    pos["partial_booked"] = True
    pos["lots_held"] = 4
    pos["current_sl"] = 100.0

    state["latest_3m_candle"] = Candle(instrument="NIFTY_FUT", timeframe="3m", timestamp=now, open=130, high=135, low=120, close=132, volume=1000)

    tick = Tick(instrument="NIFTY_FUT", price=132.0, timestamp=now)
    await engine._evaluate_position("NIFTY", tick)

    # New SL = low (120) - trailing buffer (10) = 110. It is > 100, so it updates.
    assert pos["current_sl"] == 110.0

@pytest.mark.asyncio
async def test_trailing_stop_bearish(engine, tz):
    now = datetime.now(tz)
    state = engine._get_underlying_state("NIFTY")
    pos = state["position"]
    pos["active"] = True
    pos["direction"] = "BUY_PE"
    pos["partial_booked"] = True
    pos["lots_held"] = 4
    pos["current_sl"] = 150.0

    # Bearish trailing sl moves DOWN to high + buffer
    state["latest_3m_candle"] = Candle(instrument="NIFTY_FUT", timeframe="3m", timestamp=now, open=130, high=135, low=120, close=125, volume=1000)

    tick = Tick(instrument="NIFTY_FUT", price=125.0, timestamp=now)
    await engine._evaluate_position("NIFTY", tick)

    # New SL = high (135) + trailing buffer (10) = 145. It is < 150, so it updates.
    assert pos["current_sl"] == 145.0

@pytest.mark.asyncio
async def test_tick_level_stop_breach(engine, tz):
    now = datetime.now(tz)
    state = engine._get_underlying_state("NIFTY")
    pos = state["position"]
    pos["active"] = True
    pos["direction"] = "BUY_CE"
    pos["lots_held"] = 4
    pos["current_sl"] = 110.0
    pos["avg_entry_price"] = 120.0 # Prevents accidental partial profit trigger

    tick = Tick(instrument="NIFTY_FUT", price=105.0, timestamp=now)
    # We must also ensure VWAP isn't triggering an invalidation before the SL. VWAP=0 bypasses VWAP hard invalidation.
    state["vwap"] = 0.0
    await engine._evaluate_position("NIFTY", tick)

    assert pos["active"] is False
    assert pos["lots_held"] == 0

@pytest.mark.asyncio
async def test_missing_data(engine, tz):
    now = datetime.now(tz).replace(hour=10, minute=0, second=0)
    state = engine._get_underlying_state("NIFTY")
    state["state"] = "ACTIVE"
    state["trending_oi_bullish"] = True

    # Missing daily ATR
    state["daily_atr"] = 0.0
    candle = Candle(instrument="NIFTY_FUT", timeframe="3m", timestamp=now, open=25000.0, high=25020.0, low=24992.0, close=25010.0, volume=2000)
    await engine._evaluate_entries("NIFTY", candle)
    assert state["position"]["active"] is False

@pytest.mark.asyncio
async def test_event_bus_integration(engine, tz):
    events_emitted = []
    def on_signal(sig):
        events_emitted.append(sig)
    event_bus.subscribe("STRATEGY_SIGNAL", on_signal)

    now = datetime.now(tz).replace(hour=10, minute=0, second=0)

    event_bus.start() # Ensure bus is started
    await asyncio.sleep(0.01)

    engine._update_session_state('NIFTY', now)
    state = engine._get_underlying_state('NIFTY')

    # Let's test the direct handlers since EventBus might be isolated/stubbed in tests or need loop management
    await engine.on_trending_oi({
        "type": "tick_update", "view": "spot_trending_oi", "underlying": "NIFTY",
        "row": {"directionPercent": 50.0}
    })

    state['futures_oi'] = 10000
    state['day_high'] = 25050
    state['day_low'] = 25000
    state['supertrend'] = 24990.0
    state['supertrend_direction'] = 1
    state['futures_volume_history'] = [1000] * 20
    state['daily_atr'] = 100

    tick1 = Tick(instrument="NIFTY_FUT", price=25010, timestamp=now, volume=2000)
    object.__setattr__(tick1, 'oi', 9000) # OI Decrease
    await engine.on_market_tick(tick1)

    candle_3m = Candle(instrument="NIFTY_FUT", timeframe="3m", timestamp=now, open=25000, high=25020, low=24992, close=25010, volume=2000)
    candle_3m.vwap = 25000

    # We monkeypatch emit_signal to verify without full eventbus loop
    engine_emitted = []
    async def fake_emit(*args, **kwargs):
        engine_emitted.append(args)
    engine._emit_signal = fake_emit

    await engine.on_candle_closed(candle_3m)

    assert len(engine_emitted) > 0
    assert engine_emitted[0][1] == "BUY_CE"
    await event_bus.stop()
