import pytest
from backend.app.strategies.trending_oi_engine import SpotTrendingOIEngine, FutureTrendingOIEngine
from backend.app.market_data.models import Tick
from datetime import datetime

def test_spot_trending_oi_engine():
    engine = SpotTrendingOIEngine("NIFTY")

    # 1. Spot Tick
    tick = Tick(instrument="NSE_INDEX|NIFTY", price=24000.0, timestamp=datetime.now())
    engine.process_tick(tick)

    assert engine.spot_price == 24000.0
    assert len(engine.strikes) == 15
    assert 24000.0 in engine.strikes

    # 2. Options OI Ticks
    engine.process_oi_tick("NIFTY24000CE", 150.0, 10000)
    engine.process_oi_tick("NIFTY24000PE", 140.0, 12000)

    assert engine.baseline_set == True

    row = engine.current_row
    assert row["ce_oi"] == 10000
    assert row["pe_oi"] == 12000

    # OI change
    engine.process_oi_tick("NIFTY24000CE", 160.0, 15000)
    engine.process_oi_tick("NIFTY24000PE", 130.0, 14000)

    row = engine.current_row
    assert row["chg_call_oi"] == 5000
    assert row["chg_put_oi"] == 2000
    assert row["diff_oi"] == -3000
    assert row["sentiment"] == "Bearish"
    assert row["direction"] == "BEARISH"

def test_future_trending_oi_engine():
    engine = FutureTrendingOIEngine()

    engine.process_tick(price=24100.0, oi=50000, volume=1000, spot_price=24000.0)
    row = engine.current_row
    assert row["basis"] == 100.0
    assert row["futureOi"] == 50000

    # Long buildup
    engine.process_tick(price=24150.0, oi=55000, volume=2000, spot_price=24050.0)
    row = engine.current_row
    assert row["classification"] == "LONG BUILDUP"
    assert row["oiChange"] == 5000
    assert row["priceChange"] == 50.0
