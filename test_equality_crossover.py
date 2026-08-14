import pytest
from datetime import datetime
from backend.app.strategies.trending_oi_engine import SpotTrendingOIEngine
from backend.app.market_data.models import Tick

def test_spot_trending_oi_equality_crossover():
    engine = SpotTrendingOIEngine('NIFTY')
    tick = Tick(instrument='NSE_INDEX|NIFTY', price=24000.0, timestamp=datetime.now())
    engine.process_tick(tick)

    # Init state Call > Put
    engine.process_oi_tick('NIFTY24000CE', 150.0, 20000)
    engine.process_oi_tick('NIFTY24000PE', 140.0, 10000)
    import copy
    engine.completed_rows.append(copy.deepcopy(engine.current_row))

    # State Call == Put
    engine.process_oi_tick('NIFTY24000CE', 160.0, 15000)
    engine.process_oi_tick('NIFTY24000PE', 130.0, 15000)
    assert engine.current_row['crossover'] == 'NO_CROSSOVER'
    engine.completed_rows.append(copy.deepcopy(engine.current_row))

    # New state Put > Call -> Bullish Crossover
    engine.process_oi_tick('NIFTY24000CE', 160.0, 10000)
    engine.process_oi_tick('NIFTY24000PE', 130.0, 25000)
    assert engine.current_row['crossover'] == 'BULLISH_CROSSOVER'
