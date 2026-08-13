import pytest
from datetime import datetime, timezone
from app.market_data.models import Tick
from app.market_data.processor import TickProcessor

@pytest.mark.asyncio
async def test_incremental_vwap():
    processor = TickProcessor()

    tick1 = Tick(instrument="NIFTY", price=100.0, volume=10, timestamp=datetime(2023,1,1,9,15, tzinfo=timezone.utc))
    await processor.process(tick1)

    agg = processor.aggregators[0]
    assert agg.current_candles["NIFTY"].vwap == 100.0

    tick2 = Tick(instrument="NIFTY", price=200.0, volume=10, timestamp=datetime(2023,1,1,9,16, tzinfo=timezone.utc))
    await processor.process(tick2)

    assert agg.current_candles["NIFTY"].vwap == 150.0

@pytest.mark.asyncio
async def test_candle_aggregation_no_look_ahead():
    processor = TickProcessor()

    # 5m timeframe tests
    agg = processor.aggregators[0]

    # First tick at 9:15
    t1 = Tick(instrument="NIFTY", price=100, volume=10, timestamp=datetime(2023,1,1,9,15,10, tzinfo=timezone.utc))
    await processor.process(t1)
    assert not agg.current_candles["NIFTY"].is_closed

    # Tick at 9:19
    t2 = Tick(instrument="NIFTY", price=120, volume=10, timestamp=datetime(2023,1,1,9,19,50, tzinfo=timezone.utc))
    await processor.process(t2)
    assert not agg.current_candles["NIFTY"].is_closed

    # Tick at 9:20 (triggers close of 9:15 candle)
    t3 = Tick(instrument="NIFTY", price=110, volume=10, timestamp=datetime(2023,1,1,9,20,5, tzinfo=timezone.utc))
    await processor.process(t3)

    # We can't easily assert the emitted event here without mocking event_bus, but we can verify the new candle started
    assert not agg.current_candles["NIFTY"].is_closed
    assert agg.current_candles["NIFTY"].timestamp == datetime(2023,1,1,9,20,0, tzinfo=timezone.utc)
