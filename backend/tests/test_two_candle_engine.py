import pytest
from app.strategies.two_candle_engine import evaluate_two_candle_setup

def test_evaluate_two_candle_setup_outside_window():
    result = evaluate_two_candle_setup("NIFTY", "09:30", [], {})
    assert result["status"] == "PAUSED"

def test_evaluate_two_candle_setup_volume_not_met():
    candle_data = [
        {}, {},
        {"volume": 100000},
        {"volume": 150000}
    ]
    result = evaluate_two_candle_setup("NIFTY", "10:00", candle_data, {})
    assert result["status"] == "MONITORING"
    assert result["reason"] == "Volume threshold not met"

def test_evaluate_two_candle_setup_long_condition_met():
    candle_data = [
        {}, {},
        {"volume": 150000, "close": 105, "open": 100, "low": 95},
        {"volume": 160000, "close": 110, "open": 102, "vwap": 105, "supertrend": 100, "vwma": 102, "rsi": 60}
    ]
    oi_data = {"trend": "LONG_BUILDUP"}
    result = evaluate_two_candle_setup("NIFTY", "10:00", candle_data, oi_data)
    assert result["status"] == "SIGNAL_ACTIVE"
    assert result["signal"] == "BUY_CALL"
    assert result["stop_loss"] == 95

def test_evaluate_two_candle_setup_short_condition_met():
    candle_data = [
        {}, {},
        {"volume": 150000, "close": 95, "open": 100, "high": 105},
        {"volume": 160000, "close": 90, "open": 98, "vwap": 95, "supertrend": 100, "vwma": 98, "rsi": 30}
    ]
    oi_data = {"trend": "SHORT_BUILDUP"}
    result = evaluate_two_candle_setup("NIFTY", "10:00", candle_data, oi_data)
    assert result["status"] == "SIGNAL_ACTIVE"
    assert result["signal"] == "BUY_PUT"
    assert result["stop_loss"] == 105

def test_evaluate_two_candle_setup_long_blocked_by_oversold_rsi():
    # Price/volume/OI conditions otherwise identical to the passing long
    # test, but RSI is deep oversold (5) — should be rejected, not treated
    # as a valid long simply because it's below the 80 upper bound.
    candle_data = [
        {}, {},
        {"volume": 150000, "close": 105, "open": 100, "low": 95},
        {"volume": 160000, "close": 110, "open": 102, "vwap": 105, "supertrend": 100, "vwma": 102, "rsi": 5}
    ]
    oi_data = {"trend": "LONG_BUILDUP"}
    result = evaluate_two_candle_setup("NIFTY", "10:00", candle_data, oi_data)
    assert result["status"] == "MONITORING"
    assert result["signal"] == "NONE"

def test_evaluate_two_candle_setup_short_blocked_by_overbought_rsi():
    # Price/volume/OI conditions otherwise identical to the passing short
    # test, but RSI is deep overbought (95) — should be rejected, not
    # treated as a valid short simply because it's above the 20 lower bound.
    candle_data = [
        {}, {},
        {"volume": 150000, "close": 95, "open": 100, "high": 105},
        {"volume": 160000, "close": 90, "open": 98, "vwap": 95, "supertrend": 100, "vwma": 98, "rsi": 95}
    ]
    oi_data = {"trend": "SHORT_BUILDUP"}
    result = evaluate_two_candle_setup("NIFTY", "10:00", candle_data, oi_data)
    assert result["status"] == "MONITORING"
    assert result["signal"] == "NONE"
