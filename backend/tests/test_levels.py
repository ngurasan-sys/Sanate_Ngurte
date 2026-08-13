import pytest
from datetime import datetime, timezone
from app.levels.support_resistance import SupportResistanceDetector
from app.market_data.models import Candle

def test_support_resistance_deterministic():
    detector = SupportResistanceDetector()

    candles = [
        Candle(instrument="NIFTY", timeframe="5m", timestamp=datetime(2023,1,1,9,15, tzinfo=timezone.utc), open=100, high=110, low=90, close=105, volume=100),
        Candle(instrument="NIFTY", timeframe="5m", timestamp=datetime(2023,1,1,9,20, tzinfo=timezone.utc), open=105, high=120, low=100, close=115, volume=100),
        Candle(instrument="NIFTY", timeframe="5m", timestamp=datetime(2023,1,1,9,25, tzinfo=timezone.utc), open=115, high=115, low=80, close=85, volume=100),
    ]

    # The middle candle has a higher high than the surrounding candles (120 > 110 and 120 > 115)
    # The middle candle has a higher low, so it's NOT a support.

    levels = detector.detect(candles, [])
    assert len(levels) == 1
    assert levels[0].level_type == "Resistance"
    assert levels[0].price == 120
