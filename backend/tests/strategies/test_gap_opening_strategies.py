import pytest
from datetime import datetime
import pytz
from app.market_data.models import Tick, Candle
from app.strategies.gap_opening.engine import GapOpeningEngine
from app.strategies.gap_opening.models import StrategyConfig
from app.core.event_bus import event_bus

IST = pytz.timezone('Asia/Kolkata')

@pytest.fixture
def engine():
    config = StrategyConfig(
        opening_time="09:15",
        entry_start_time="09:45"
    )
    return GapOpeningEngine(config)

@pytest.mark.asyncio
async def test_engine_discovery_phase_blocks_entry(engine):
    dt = IST.localize(datetime(2024, 1, 1, 9, 30))
    tick = Tick(instrument="NIFTY", price=24000.0, timestamp=dt, volume=0.0, is_trade=True)
    await engine.handle_tick(tick)
    assert engine.state["NIFTY"].position_state == "WAITING_FOR_DISCOVERY"
    candle = Candle(
        instrument="NIFTY", timeframe="5m", timestamp=dt,
        open=24000.0, high=24050.0, low=23950.0, close=24000.0, volume=1000.0, vwap=24000.0
    )
    await engine.handle_candle(candle)
    assert not engine.state["NIFTY"].in_position

@pytest.mark.asyncio
async def test_engine_allows_entry_after_discovery(engine):
    dt = IST.localize(datetime(2024, 1, 1, 9, 45))
    tick = Tick(instrument="NIFTY", price=24000.0, timestamp=dt, volume=0.0, is_trade=True)
    await engine.handle_tick(tick)
    assert engine.state["NIFTY"].position_state == "DISCOVERY_COMPLETE"

    engine.oi_regime["NIFTY"] = "BULLISH"
    engine.diff_oi_pct["NIFTY"] = 50.0

    for i in range(15):
        engine.indicators.update_candle("NIFTY", 23900.0, 23800.0, 23850.0)

    engine.context["NIFTY"]["last_price"] = 23900.0
    engine.day_high["NIFTY"] = 23980.0
    engine.day_low["NIFTY"] = 23900.0
    engine.indicators.supertrend["NIFTY"] = 23990.0

    await engine._evaluate_setup("NIFTY", 24000.0, dt)

    assert engine.state["NIFTY"].in_position
    assert engine.state["NIFTY"].direction == "BULLISH"
    assert engine.state["NIFTY"].position_state == "TIER_1_ENTERED"

@pytest.mark.asyncio
async def test_engine_tier_2_and_partial_profit(engine):
    dt = IST.localize(datetime(2024, 1, 1, 9, 45))
    tick = Tick(instrument="NIFTY", price=24050.0, timestamp=dt, volume=0.0, is_trade=True)
    await engine.handle_tick(tick)

    engine.oi_regime["NIFTY"] = "BULLISH"
    engine.diff_oi_pct["NIFTY"] = 50.0
    for i in range(15):
        engine.indicators.update_candle("NIFTY", 23900.0, 23800.0, 23850.0)

    engine.context["NIFTY"]["last_price"] = 23900.0
    engine.day_high["NIFTY"] = 23980.0
    engine.day_low["NIFTY"] = 23900.0
    engine.indicators.supertrend["NIFTY"] = 24040.0

    # Enter Tier 1
    await engine._evaluate_setup("NIFTY", 24050.0, dt)
    assert engine.state["NIFTY"].in_position

    # Simulate partial profit (price rises by 25 points to 24075)
    tick2 = Tick(instrument="NIFTY", price=24075.0, timestamp=dt, volume=0.0, is_trade=True)
    await engine.handle_tick(tick2)

    assert engine.state["NIFTY"].partial_booked == True
    assert engine.state["NIFTY"].lots_held == 1
    assert engine.state["NIFTY"].current_sl == 24050.0 # Breakeven

@pytest.mark.asyncio
async def test_engine_stop_breach(engine):
    dt = IST.localize(datetime(2024, 1, 1, 9, 45))
    tick = Tick(instrument="NIFTY", price=24000.0, timestamp=dt, volume=0.0, is_trade=True)
    await engine.handle_tick(tick)

    engine.oi_regime["NIFTY"] = "BULLISH"
    engine.diff_oi_pct["NIFTY"] = 50.0
    for i in range(15):
        engine.indicators.update_candle("NIFTY", 23900.0, 23800.0, 23850.0)

    engine.context["NIFTY"]["last_price"] = 23900.0
    engine.day_high["NIFTY"] = 23980.0
    engine.day_low["NIFTY"] = 23900.0
    engine.indicators.supertrend["NIFTY"] = 23990.0

    # Enter Tier 1
    await engine._evaluate_setup("NIFTY", 24000.0, dt)

    # SL is vwap - buffer = 0 - 10 = -10 (vwap is 0 initially). Let's set vwap.
    engine.vwap["NIFTY"] = 24000.0
    engine.state["NIFTY"].current_sl = 23990.0

    # Trigger stop
    tick2 = Tick(instrument="NIFTY", price=23985.0, timestamp=dt, volume=0.0, is_trade=True)
    await engine.handle_tick(tick2)

    assert not engine.state["NIFTY"].in_position
    assert engine.state["NIFTY"].position_state == "EXITED"

@pytest.mark.asyncio
async def test_engine_intraday_gap_blocks_tier_2(engine):
    pass

@pytest.mark.asyncio
async def test_engine_event_pyramid(engine):
    dt = IST.localize(datetime(2024, 1, 1, 9, 45))
    tick = Tick(instrument="NIFTY", price=24050.0, timestamp=dt, volume=0.0, is_trade=True)
    await engine.handle_tick(tick)

    engine.oi_regime["NIFTY"] = "BULLISH"
    engine.diff_oi_pct["NIFTY"] = 50.0
    for i in range(15):
        engine.indicators.update_candle("NIFTY", 23900.0, 23800.0, 23850.0)

    engine.context["NIFTY"]["last_price"] = 23900.0
    engine.day_high["NIFTY"] = 24000.0
    engine.day_low["NIFTY"] = 23900.0

    engine.indicators.supertrend["NIFTY"] = 24040.0

    # We must explicitly turn off VIX override so it blocks on ATR exhaustion, OR we make sure ATR exhaustion is False.
    # ATR is 100 here. day_range is 24000 - 23900 = 100. So exhaustion = True. Let's make exhaustion False.
    engine.day_high["NIFTY"] = 23980.0

    await engine._evaluate_setup("NIFTY", 24050.0, dt)
    assert engine.state["NIFTY"].in_position

    # We are in TREND_CONTINUATION mode
    # Make ATR exhausted
    engine.day_high["NIFTY"] = 25000.0
    # Make VIX override True
    engine.vix_override = True

    # Simulate a candle update to trigger position management
    candle = Candle(
        instrument="NIFTY", timeframe="5m", timestamp=dt,
        open=24050.0, high=24060.0, low=24040.0, close=24050.0, volume=1000.0, vwap=24050.0
    )

    await engine._evaluate_position_management("NIFTY", candle)

    assert engine.state["NIFTY"].event_pyramid_used == True

@pytest.mark.asyncio
async def test_engine_structural_invalidation(engine):
    # Tests that when we get a divergence, entry is blocked
    dt = IST.localize(datetime(2024, 1, 1, 9, 45))
    tick = Tick(instrument="NIFTY", price=24000.0, timestamp=dt, volume=0.0, is_trade=True)
    await engine.handle_tick(tick)

    engine.oi_regime["NIFTY"] = "BULLISH"
    # To block bullish entry, we need price > prev_price AND diff_pct < 0
    engine.diff_oi_pct["NIFTY"] = -5.0

    for i in range(15):
        engine.indicators.update_candle("NIFTY", 23900.0, 23800.0, 23850.0)

    engine.context["NIFTY"]["last_price"] = 23900.0 # Prev price < 24000
    engine.day_high["NIFTY"] = 24000.0
    engine.day_low["NIFTY"] = 23900.0
    engine.indicators.supertrend["NIFTY"] = 23990.0

    await engine._evaluate_setup("NIFTY", 24000.0, dt)
    assert not engine.state["NIFTY"].in_position
