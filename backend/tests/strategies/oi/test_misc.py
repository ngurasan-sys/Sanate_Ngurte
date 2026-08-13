import pytest
from datetime import datetime
from backend.app.oi.models import OIState, OITick
from backend.app.strategies.oi.unusual_oi import UnusualOIStrategy
from backend.app.strategies.oi.oi_support_resistance import OISupportResistanceStrategy
from backend.app.strategies.oi.oi_breakout import OIBreakoutStrategy
from backend.app.strategies.oi.oi_price_divergence import OIPriceDivergenceStrategy

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
        rolling_oi_changes=[10, -5, 12, 8, -10, 15]
    )

def test_unusual_oi(base_state):
    strategy = UnusualOIStrategy()

    # Needs a huge spike relative to rolling changes
    base_state.previous_oi = 1000
    base_state.current_oi = 2000 # +1000 change vs ~10 avg

    signal = strategy.analyze(OITick(instrument="NIFTY", timestamp=datetime.now()), base_state)
    assert signal is not None
    assert signal.signal_type == "ALERT"

def test_support_resistance(base_state):
    strategy = OISupportResistanceStrategy()

    base_state.strike = 19000
    base_state.ce_oi = 50000
    base_state.pe_oi = 10000

    # High CE -> Resistance
    signal = strategy.analyze(OITick(instrument="NIFTY", timestamp=datetime.now()), base_state)
    assert signal is not None
    assert signal.signal_type == "RESISTANCE"

def test_breakout(base_state):
    strategy = OIBreakoutStrategy()

    # >5% expansion + price up
    base_state.previous_oi = 1000
    base_state.current_oi = 1100 # 10%
    base_state.previous_price = 100
    base_state.current_price = 105

    signal = strategy.analyze(OITick(instrument="NIFTY", timestamp=datetime.now()), base_state)
    assert signal is not None
    assert signal.signal_type == "BREAKOUT"

def test_divergence(base_state):
    strategy = OIPriceDivergenceStrategy()

    # Price Up >1%, OI Down >1%
    base_state.previous_price = 100
    base_state.current_price = 102 # +2%
    base_state.previous_oi = 1000
    base_state.current_oi = 950 # -5%

    signal = strategy.analyze(OITick(instrument="NIFTY", timestamp=datetime.now()), base_state)
    assert signal is not None
    assert signal.signal_type == "DIVERGENCE"
    assert signal.direction == "BEARISH" # Price up but OI down is bearish