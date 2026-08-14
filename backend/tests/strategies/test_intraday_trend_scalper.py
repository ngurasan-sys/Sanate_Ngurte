import pytest
import asyncio
from datetime import datetime, time
from backend.app.market_data.models import Candle, Tick
from backend.app.strategies.intraday_trend_scalper.engine import intraday_trend_scalper

@pytest.fixture
def engine():
    intraday_trend_scalper.start()
    # Reset state for tests
    intraday_trend_scalper.positions.clear()
    intraday_trend_scalper.daily_trades_count = 0
    intraday_trend_scalper.current_date = None
    yield intraday_trend_scalper
    intraday_trend_scalper.stop()

def create_candle(time_str: str, close: float, vwap: float, high: float, low: float) -> Candle:
    # Use 2024-01-01 as default test date
    dt = datetime.strptime(f"2024-01-01 {time_str}", "%Y-%m-%d %H:%M:%S")
    return Candle(
        instrument="NIFTY FUT",
        timeframe="3m",
        timestamp=dt,
        open=close, # simplify open
        high=high,
        low=low,
        close=close,
        volume=1000,
        vwap=vwap,
        is_closed=True
    )

def create_tick(price: float) -> Tick:
    return Tick(
        instrument="NIFTY FUT",
        price=price,
        volume=10,
        timestamp=datetime.now(),
        is_trade=True
    )

@pytest.mark.asyncio
async def test_time_filter_before_0930(engine):
    candle = create_candle("09:15:00", 20000, 20000, 20050, 19950)
    await engine._handle_candle_closed(candle)

    state = engine._get_instrument_state("NIFTY FUT")
    assert state["state"] == "WAITING_FOR_OPEN"

@pytest.mark.asyncio
async def test_time_filter_after_1400(engine):
    candle = create_candle("14:05:00", 20000, 20000, 20050, 19950)
    await engine._handle_candle_closed(candle)

    state = engine._get_instrument_state("NIFTY FUT")
    assert state["state"] == "TIME_BLOCKED"

@pytest.mark.asyncio
async def test_oi_confirmation_parsing(engine):
    payload = {
        "view": "spot_trending_oi",
        "underlying": "NIFTY",
        "row": {
            "differenceOi": 4500000
        }
    }

    await engine._handle_trending_oi(payload)
    state = engine._get_instrument_state("NIFTY FUT")
    assert state["bullish_oi_confirmed"] is True
    assert state["bearish_oi_confirmed"] is False

@pytest.mark.asyncio
async def test_bullish_trend_confirmation_and_pullback(engine):
    # Set OI Confirmed
    await engine._handle_trending_oi({"view": "spot_trending_oi", "row": {"differenceOi": 4500000}})

    # 09:30 candle, close > vwap, trend=1 (force it by setting state or via supertrend calc)
    state = engine._get_instrument_state("NIFTY FUT")
    state["trend"] = 1 # Mock supertrend result for test simplicity
    state["supertrend"] = 19900

    # Pre-existing day high should be lower than breakout close
    state["current_day_high"] = 20080

    # Breakout candle
    breakout_candle = create_candle("09:45:00", 20100, 20000, 20150, 20050)
    await engine._handle_candle_closed(breakout_candle)

    assert state["state"] == "BULLISH_TREND_CONFIRMED"

    # Pullback candle (touches VWAP + buffer)
    pullback_candle = create_candle("09:48:00", 20050, 20000, 20080, 20002)
    # Re-apply trend=1 because add_candle will override it with 0 if not enough data
    state["trend"] = 1
    await engine._handle_candle_closed(pullback_candle)

    assert state["state"] == "ENTRY_TIER_1"
    assert state["lots_held"] == 2
    assert engine.daily_trades_count == 1

@pytest.mark.asyncio
async def test_daily_limit_reached(engine):
    engine.daily_trades_count = 3
    engine.current_date = datetime.strptime("2024-01-01", "%Y-%m-%d").date()
    candle = create_candle("10:00:00", 20000, 20000, 20050, 19950)
    await engine._handle_candle_closed(candle)

    state = engine._get_instrument_state("NIFTY FUT")
    assert state["state"] == "DAILY_LIMIT_REACHED"

@pytest.mark.asyncio
async def test_vwap_invalidation(engine):
    engine.current_date = datetime.strptime("2024-01-01", "%Y-%m-%d").date()
    state = engine._get_instrument_state("NIFTY FUT")
    state["state"] = "ENTRY_TIER_1"
    state["position_direction"] = 1 # Added the missing setup state
    state["lots_held"] = 2
    state["last_vwap"] = 20000

    # Candle closes below VWAP
    candle = create_candle("10:00:00", 19900, 20000, 19950, 19850)
    await engine._handle_candle_closed(candle)

    assert state["state"] == "INVALIDATED"
    assert state["lots_held"] == 0

@pytest.mark.asyncio
async def test_hard_stop_loss_tick(engine):
    state = engine._get_instrument_state("NIFTY FUT")
    state["state"] = "ENTRY_TIER_1"
    state["position_direction"] = 1
    state["lots_held"] = 2
    state["current_sl"] = 19900

    # Tick below SL
    tick = create_tick(19850)
    await engine._handle_market_tick(tick)

    assert state["state"] == "EXITED"
    assert state["lots_held"] == 0

@pytest.mark.asyncio
async def test_oi_conviction_loss_during_active_trade(engine):
    engine.current_date = datetime.strptime("2024-01-01", "%Y-%m-%d").date()
    state = engine._get_instrument_state("NIFTY FUT")
    state["state"] = "ENTRY_TIER_1"
    state["position_direction"] = 1 # Bullish
    state["lots_held"] = 2
    state["avg_entry_price"] = 20000
    state["current_sl"] = 19900
    state["last_vwap"] = 20000

    # Tick tests (should not trigger bearish stop loss logic, should wait for bullish stop)
    # Even if tick.price > sl (which is true for 19950 > 19900), it should NOT exit because it's a bullish trade
    # And it shouldn't trigger partial profit (diff < 20)
    tick = create_tick(19950)
    await engine._handle_market_tick(tick)
    assert state["state"] == "ENTRY_TIER_1" # Still active

    # Candle tests (should not hit bearish VWAP invalidation)
    # Candle closes at 19950 (below VWAP), should correctly hit the BULLISH VWAP invalidation
    candle = create_candle("10:00:00", 19950, 20000, 19960, 19940)
    await engine._handle_candle_closed(candle)
    assert state["state"] == "INVALIDATED"

@pytest.mark.asyncio
async def test_partial_profit_and_break_even(engine):
    state = engine._get_instrument_state("NIFTY FUT")
    state["state"] = "ENTRY_TIER_1"
    state["position_direction"] = 1
    state["lots_held"] = 4 # simulate bigger pos
    state["avg_entry_price"] = 20000
    state["current_sl"] = 19950
    state["partial_profit_taken"] = False

    # Tick hits 20025 (>= 20 points profit)
    tick = create_tick(20025)
    await engine._handle_market_tick(tick)

    assert state["partial_profit_taken"] is True
    assert state["state"] == "BREAK_EVEN"
    assert state["lots_held"] == 2 # 50% exit
    assert state["current_sl"] == 20000 # Moved to break even
