import pytest
from datetime import datetime
from backend.app.oi.engine import OIEngine
from backend.app.oi.models import OITick

def test_engine_initialization():
    engine = OIEngine()
    assert len(engine.states) == 0

def test_engine_process_first_tick():
    engine = OIEngine()
    tick = OITick(
        instrument="NIFTY_23NOV",
        timestamp=datetime.now(),
        price=19000,
        oi=1000
    )

    state = engine.process_tick(tick)
    assert state is not None
    assert state.current_price == 19000
    assert state.current_oi == 1000
    assert state.previous_oi == 0
    assert len(state.rolling_oi_changes) == 0

def test_engine_incremental_update():
    engine = OIEngine()

    # Tick 1
    engine.process_tick(OITick(
        instrument="NIFTY_23NOV",
        timestamp=datetime.now(),
        price=19000,
        oi=1000
    ))

    # Tick 2
    state = engine.process_tick(OITick(
        instrument="NIFTY_23NOV",
        timestamp=datetime.now(),
        price=19050,
        oi=1500
    ))

    assert state.previous_price == 19000
    assert state.current_price == 19050
    assert state.previous_oi == 1000
    assert state.current_oi == 1500
    assert state.rolling_oi_changes == [500]

def test_engine_missing_data_tick():
    engine = OIEngine()

    engine.process_tick(OITick(
        instrument="NIFTY_23NOV",
        timestamp=datetime.now(),
        price=19000,
        oi=1000
    ))

    # Tick with missing OI - shouldn't update OI
    state = engine.process_tick(OITick(
        instrument="NIFTY_23NOV",
        timestamp=datetime.now(),
        price=19050,
        oi=None
    ))

    assert state.current_price == 19050
    assert state.current_oi == 1000 # Unchanged

def test_engine_empty_tick():
    engine = OIEngine()
    # If a tick has no meaningful data, it returns None or existing state without mutating
    state = engine.process_tick(OITick(
        instrument="NIFTY_23NOV",
        timestamp=datetime.now()
    ))
    assert state is None