import pytest
import asyncio
from datetime import datetime, time, timezone
from backend.app.strategies.trending_oi_price_action.engine import TrendingOIPriceActionStrategy
from backend.app.market_data.models import Candle, Tick
from backend.app.core.event_bus import event_bus
from backend.app.market_data.processor import TickProcessor

@pytest.fixture
def engine():
    engine = TrendingOIPriceActionStrategy()
    # Mocking event_bus globally can be tricky if we don't start it, but engine works directly mostly
    return engine

@pytest.mark.asyncio
async def test_time_barriers(engine):
    assert engine._is_discovery_period(time(9, 15)) == True
    assert engine._is_discovery_period(time(9, 30)) == True
    assert engine._is_discovery_period(time(9, 44, 59)) == True
    assert engine._is_discovery_period(time(9, 45)) == False
    assert engine._is_discovery_period(time(10, 0)) == False

@pytest.mark.asyncio
async def test_bullish_setup(engine):
    engine.start()

    # 1. Setup trending OI
    await engine._handle_trending_oi({
        "view": "spot_trending_oi",
        "underlying": "NIFTY",
        "row": {
            "directionPercent": 50.0,
            "strength": 30 # 3 dots
        }
    })

    state = engine._get_instrument_state("NIFTY FUT")
    assert state["bullish_oi_confirmed"] == True

    # 2. Add candles (1d to set ATR)
    dt1 = datetime(2023, 1, 1, tzinfo=timezone.utc)
    for i in range(15):
        await engine._handle_candle_closed(Candle(
            instrument="NIFTY FUT", timeframe="1d", timestamp=dt1,
            open=100, high=120, low=80, close=110, volume=1000
        ))

    state = engine._get_instrument_state("NIFTY FUT")
    assert state["daily_atr"].atr_values[-1] > 0

    # 3. Add intraday 3m candles (Post discovery)
    dt2 = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc) # 10:00 > 9:45
    # Build up Supertrend to get trend=1
    for i in range(15):
        await engine._handle_candle_closed(Candle(
            instrument="NIFTY FUT", timeframe="3m", timestamp=dt2,
            open=100, high=110+i, low=90+i, close=105+i, volume=100, vwap=100+i
        ))

    assert state["supertrend"].trend[-1] == 1
    st_val = state["supertrend"].supertrend[-1]

    # 4. Trigger pullback
    state["position_state"] = "WAITING"

    # Clean false breakout flags
    state["false_breakout"] = False
    state["resistance_rejections"] = 0

    # Notice we must mock the engine call because _execute_signal fires
    # immediately if BULLISH_SETUP is entered. We check if it sets to TIER_1_ENTERED
    await engine._handle_candle_closed(Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=dt2,
        open=st_val + 15, high=st_val + 20, low=st_val - 2, close=st_val + 5, volume=100, vwap=st_val - 1
    ))

    assert state["position_state"] in ["BULLISH_SETUP", "TIER_1_ENTERED"]

    # Reset event bus before assertions if integration needed, but internal state tells us it worked.

@pytest.mark.asyncio
async def test_resistance_rejection_and_false_breakout(engine):
    engine.start()

    dt1 = datetime(2023, 1, 1, 9, 30, tzinfo=timezone.utc)
    state = engine._get_instrument_state("NIFTY FUT")
    state["current_day_high"] = 100

    # 1. Establish resistance
    await engine._handle_candle_closed(Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=dt1,
        open=100, high=100, low=90, close=94, volume=100
    ))
    assert state["resistance_level"] == 100
    assert state["resistance_rejections"] == 1

    # 2. Reject again
    dt2 = datetime(2023, 1, 1, 9, 33, tzinfo=timezone.utc)
    await engine._handle_candle_closed(Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=dt2,
        open=100, high=100, low=90, close=94, volume=100
    ))
    assert state["resistance_rejections"] == 2

    # 3. False Breakout
    dt3 = datetime(2023, 1, 1, 9, 36, tzinfo=timezone.utc)
    await engine._handle_candle_closed(Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=dt3,
        open=100, high=105, low=90, close=99, volume=100 # High > 100, Close < 100
    ))
    assert state["false_breakout"] == True

    # 4. Reject 3rd time (blocks trades)
    dt4 = datetime(2023, 1, 1, 9, 39, tzinfo=timezone.utc)
    await engine._handle_candle_closed(Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=dt4,
        open=100, high=100, low=90, close=94, volume=100
    ))
    assert state["resistance_rejections"] == 3

    # Enable trading timeframe and conditions
    dt5 = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
    await engine._handle_trending_oi({"view": "spot_trending_oi", "underlying": "NIFTY", "row": {"directionPercent": 50, "strength": 30}})
    state["supertrend"].trend = [1]
    state["supertrend"].supertrend = [80]
    state["last_vwap"] = 80

    # Try trigger setup, should be blocked by fake breakout & rejection limits
    await engine._handle_candle_closed(Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=dt5,
        open=85, high=90, low=81, close=82, volume=100
    ))

    assert state["position_state"] == "WAITING"

@pytest.mark.asyncio
async def test_full_integration():
    event_bus._pending_subscriptions.clear()
    event_bus._subscriber_queues.clear()
    event_bus._workers.clear()
    event_bus._started = False
    event_bus.start()

    processor = TickProcessor()
    engine = TrendingOIPriceActionStrategy()
    engine.start()

    captured_signals = []
    async def capture(d):
        captured_signals.append(d)

    event_bus.subscribe("STRATEGY_SIGNAL", capture)

    # Just a simple sanity test ensuring no crash and logic is sound
    await engine._handle_trending_oi({"view": "spot_trending_oi", "row": {"directionPercent": 50, "strength": 30}})

    dt2 = datetime(2023, 1, 1, 10, 0, tzinfo=timezone.utc)
    for i in range(15):
        await processor.process(Tick(instrument="NIFTY FUT", price=100+i, timestamp=dt2))

    # Let event bus run
    await asyncio.sleep(0.1)

    # Engine logic was tested in unit tests, integration just checks it wires up.
    engine.stop()
    event_bus.stop()
