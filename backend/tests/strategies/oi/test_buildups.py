import pytest
from datetime import datetime
from app.oi.models import OIState, OITick
from app.strategies.oi.long_buildup import LongBuildupStrategy
from app.strategies.oi.short_buildup import ShortBuildupStrategy
from app.strategies.oi.long_unwinding import LongUnwindingStrategy
from app.strategies.oi.short_covering import ShortCoveringStrategy

@pytest.fixture
def base_state():
    return OIState(
        instrument="NIFTY",
        last_update=datetime.now(),
        previous_price=100,
        current_price=105,
        previous_oi=1000,
        current_oi=1100,
        vwap=102,
        previous_volume=1000,
        current_volume=2000
    )

def test_long_buildup(base_state):
    strategy = LongBuildupStrategy()

    # Price Up, OI Up -> Long Buildup
    signal = strategy.analyze(OITick(instrument="NIFTY", timestamp=datetime.now()), base_state)
    assert signal is not None
    assert signal.direction == "BULLISH"
    assert signal.oi_state == "INCREASING"
    assert signal.price_state == "INCREASING"

def test_short_buildup(base_state):
    strategy = ShortBuildupStrategy()

    # Price Down, OI Up -> Short Buildup
    base_state.current_price = 95
    base_state.vwap = 98
    signal = strategy.analyze(OITick(instrument="NIFTY", timestamp=datetime.now()), base_state)
    assert signal is not None
    assert signal.direction == "BEARISH"

def test_long_unwinding(base_state):
    strategy = LongUnwindingStrategy()

    # Price Down, OI Down -> Long Unwinding
    base_state.current_price = 95
    base_state.current_oi = 900
    signal = strategy.analyze(OITick(instrument="NIFTY", timestamp=datetime.now()), base_state)
    assert signal is not None
    assert signal.direction == "BEARISH"
    assert signal.signal_type == "EXIT"

def test_short_covering(base_state):
    strategy = ShortCoveringStrategy()

    # Price Up, OI Down -> Short Covering
    base_state.current_price = 105
    base_state.current_oi = 900
    signal = strategy.analyze(OITick(instrument="NIFTY", timestamp=datetime.now()), base_state)
    assert signal is not None
    assert signal.direction == "BULLISH"
    assert signal.signal_type == "EXIT"