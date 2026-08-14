import pytest
from datetime import datetime
from app.strategies.oh_ol.oh_ol_strategy import OhOlStrategy
from app.strategies.oh_ol.oh_ol_strategy import TargetState, OhOlState
from app.market_data.models import Tick
from app.oi.models import OITick

def test_detect_oh_exact():
    strategy = OhOlStrategy()
    assert strategy.detect_oh(100.0, 100.0) is True

def test_detect_oh_within_tolerance():
    strategy = OhOlStrategy()
    # 0.05% of 100 is 0.05
    assert strategy.detect_oh(100.0, 100.04) is True

def test_detect_oh_outside_tolerance():
    strategy = OhOlStrategy()
    assert strategy.detect_oh(100.0, 100.06) is False

def test_detect_ol_exact():
    strategy = OhOlStrategy()
    assert strategy.detect_ol(100.0, 100.0) is True

def test_detect_ol_within_tolerance():
    strategy = OhOlStrategy()
    assert strategy.detect_ol(100.0, 99.96) is True

def test_detect_ol_outside_tolerance():
    strategy = OhOlStrategy()
    assert strategy.detect_ol(100.0, 99.94) is False

@pytest.mark.asyncio
async def test_process_tick_target_generation():
    strategy = OhOlStrategy()
    strategy.start()

    tick1 = Tick(instrument="NIFTY_FUT", price=100.0, timestamp=datetime.now())
    await strategy.process_tick(tick1)

    assert len(strategy.targets) == 2  # Both OH and OL created at initialization
    assert strategy.targets[0].target_type == "OH"
    assert strategy.targets[0].target_price == 100.0

    tick2 = Tick(instrument="NIFTY_FUT", price=101.0, timestamp=datetime.now())
    await strategy.process_tick(tick2)

@pytest.mark.asyncio
async def test_no_duplicate_signals():
    strategy = OhOlStrategy()
    strategy.start()

    # Send an OI tick that satisfies morning condition
    strategy.total_call_oi_change = 2000
    strategy.total_put_oi_change = 1000  # Ratio 2.0 > 1.8
    strategy.current_supertrend_dir = -1
    strategy.vwap = 100.0

    tick = OITick(
        instrument="NIFTY",
        timestamp=datetime.now(),
        price=99.9, # Below VWAP, very close
        ce_oi_change=0,
        pe_oi_change=0
    )

    await strategy.process_oi_tick(tick)
    assert strategy.active_position is True

    # A second tick should not generate another signal since active_position is True
    # We could mock the event bus to verify `publish` is called exactly once,
    # but the simplest way is to check the `active_position` logic doesn't throw or reset.
    last_signal_time = strategy.last_signal_time
    await strategy.process_oi_tick(tick)
    assert strategy.last_signal_time == last_signal_time

@pytest.mark.asyncio
async def test_opening_probability_filter():
    strategy = OhOlStrategy()
    strategy.start()
    strategy.opening_prob_threshold = 90.0

    # 09:15
    tick_early = Tick(instrument="NIFTY_FUT", price=100.0, timestamp=datetime.strptime("09:15:00", "%H:%M:%S"))
    await strategy.process_tick(tick_early)

    tick_early2 = Tick(instrument="NIFTY_FUT", price=100.0, timestamp=datetime.strptime("09:15:01", "%H:%M:%S"))
    await strategy.process_tick(tick_early2)

    assert len(strategy.targets) == 2
    oh_target = strategy.targets[0]
    # In order to trigger evaluate candidates correctly and not get skipped by consumed/active/exited
    oh_target.active = True
    oh_target.consumed = False

    # probability < 90
    assert oh_target.state == OhOlState.O_H_OPENING_BLOCKED

    # 09:30
    tick_late = Tick(instrument="NIFTY_FUT", price=101.0, timestamp=datetime.strptime("09:30:00", "%H:%M:%S"))
    await strategy.process_tick(tick_late)

    # Opening block removed at 09:30
    assert oh_target.state in [OhOlState.O_H_DETECTED, OhOlState.O_H_CONFIRMED, OhOlState.O_H_WAITING_PULLBACK]

@pytest.mark.asyncio
async def test_oi_shift_confirmation():
    strategy = OhOlStrategy()
    strategy.start()
    strategy.min_oi_shift = 500000.0

    tick = Tick(instrument="NIFTY_FUT", price=100.0, timestamp=datetime.strptime("09:35:00", "%H:%M:%S"))
    await strategy.process_tick(tick)

    tick2 = Tick(instrument="NIFTY_FUT", price=100.0, timestamp=datetime.strptime("09:35:01", "%H:%M:%S"))
    await strategy.process_tick(tick2)

    oh_target = strategy.targets[0]
    # In order to trigger evaluate candidates correctly and not get skipped by consumed/active/exited
    oh_target.active = True
    oh_target.consumed = False
    assert oh_target.state == OhOlState.O_H_DETECTED

    # Simulate trending OI update
    await strategy._handle_trending_oi({
        "type": "tick_update",
        "view": "spot_trending_oi",
        "underlying": "NIFTY_FUT",
        "row": {
            "differenceOi": 600000.0,
            "strength": 100
        }
    })

    assert oh_target.oi_shift == 600000.0

    # Process another tick to run evaluation
    tick_conf = Tick(instrument="NIFTY_FUT", price=102.0, timestamp=datetime.strptime("09:36:00", "%H:%M:%S"))
    await strategy.process_tick(tick_conf)

    # Should be confirmed now (breakout confirmed because price 102 > day high 100)
    assert oh_target.state == OhOlState.O_H_WAITING_PULLBACK

@pytest.mark.asyncio
async def test_atr_exhaustion_blocks_entry():
    strategy = OhOlStrategy()
    strategy.start()

    tick = Tick(instrument="NIFTY_FUT", price=100.0, timestamp=datetime.strptime("09:35:00", "%H:%M:%S"))
    await strategy.process_tick(tick)

    state = strategy._get_or_create_instrument_state("NIFTY_FUT")
    state["previous_day_close"] = 90.0
    # Simulate ATR of 5
    state["daily_atr"].atr_values.append(5.0)

    oh_target = strategy.targets[0]
    # In order to trigger evaluate candidates correctly and not get skipped by consumed/active/exited
    oh_target.active = True
    oh_target.consumed = False

    tick2 = Tick(instrument="NIFTY_FUT", price=100.0, timestamp=datetime.strptime("09:35:01", "%H:%M:%S"))
    await strategy.process_tick(tick2)

    # Price moved 10 points (100 - 90), which is >= ATR of 5
    assert oh_target.atr_exhausted is True

@pytest.mark.asyncio
async def test_pullback_tier_1_and_2():
    strategy = OhOlStrategy()
    strategy.start()
    strategy.vwap = 98.0
    strategy.current_supertrend = 99.0

    tick = Tick(instrument="NIFTY_FUT", price=100.0, timestamp=datetime.strptime("09:35:00", "%H:%M:%S"))
    await strategy.process_tick(tick)

    tick2 = Tick(instrument="NIFTY_FUT", price=100.0, timestamp=datetime.strptime("09:35:01", "%H:%M:%S"))
    await strategy.process_tick(tick2)

    oh_target = strategy.targets[0]
    # In order to trigger evaluate candidates correctly and not get skipped by consumed/active/exited
    oh_target.active = True
    oh_target.consumed = False
    oh_target.tested = False # Reset tested flag since hitting 100 on earlier tick tested the OH!
    oh_target.state = OhOlState.O_H_WAITING_PULLBACK

    # Pullback to Supertrend
    tick_st = Tick(instrument="NIFTY_FUT", price=99.0, timestamp=datetime.strptime("09:36:00", "%H:%M:%S"))
    await strategy.process_tick(tick_st)

    assert oh_target.state == OhOlState.O_H_TIER_1
    assert oh_target.tier == 1
    assert oh_target.lots == strategy.tier_1_lots

    # Pullback to VWAP
    tick_vwap = Tick(instrument="NIFTY_FUT", price=98.0, timestamp=datetime.strptime("09:37:00", "%H:%M:%S"))
    await strategy.process_tick(tick_vwap)

    assert oh_target.state == OhOlState.O_H_TIER_2
    assert oh_target.tier == 2
    assert oh_target.lots == strategy.tier_1_lots + strategy.tier_2_lots

@pytest.mark.asyncio
async def test_vwap_close_invalidation():
    from app.market_data.models import Candle

    strategy = OhOlStrategy()
    strategy.start()
    strategy.vwap = 98.0

    tick = Tick(instrument="NIFTY_FUT", price=100.0, timestamp=datetime.strptime("09:35:00", "%H:%M:%S"))
    await strategy.process_tick(tick)

    tick2 = Tick(instrument="NIFTY_FUT", price=100.0, timestamp=datetime.strptime("09:35:01", "%H:%M:%S"))
    await strategy.process_tick(tick2)

    oh_target = strategy.targets[0]
    # In order to trigger evaluate candidates correctly and not get skipped by consumed/active/exited
    oh_target.active = True
    oh_target.consumed = False
    oh_target.state = OhOlState.O_H_TIER_1

    # Invalidating 3m candle close
    candle = Candle(
        instrument="NIFTY_FUT",
        timeframe="3m",
        timestamp=datetime.strptime("09:39:00", "%H:%M:%S"),
        open=99.0,
        high=99.0,
        low=97.0,
        close=97.0,
        volume=100.0,
        is_closed=True
    )

    await strategy._handle_candle_closed(candle)

    assert oh_target.state == OhOlState.INVALIDATED
    assert getattr(oh_target, 'active', True) is False
