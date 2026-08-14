import pytest
from datetime import datetime
from app.strategies.oh_ol.oh_ol_strategy import OhOlStrategy, TargetState
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
