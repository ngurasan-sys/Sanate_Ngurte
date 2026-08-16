from datetime import datetime, timedelta, timezone

from backend.app.order_flow.footprint_candle import FootprintCandle
from backend.app.order_flow.models import FootprintNode
from backend.app.strategies.order_flow_absorption.absorption import (
    detect_seller_absorption, detect_buyer_absorption,
)

BASE_TIME = datetime(2024, 10, 1, 9, 30, tzinfo=timezone.utc)


def _node(price, bid, ask):
    return FootprintNode(price=price, bid_volume=bid, ask_volume=ask, total_volume=bid + ask, delta=ask - bid)


def _candle(idx, open_, high, low, close, footprint):
    return FootprintCandle(
        instrument_key="NIFTY FUT", timeframe="1m", open_time=BASE_TIME + timedelta(minutes=idx),
        open=open_, high=high, low=low, close=close, is_closed=True,
        footprint=footprint,
        buy_volume=sum(n.ask_volume for n in footprint.values()),
        sell_volume=sum(n.bid_volume for n in footprint.values()),
        delta=sum(n.ask_volume - n.bid_volume for n in footprint.values()),
    )


def _seller_absorption_candles(location=100.0):
    """Three candles: heavy aggressive selling (high bid_volume) attacking
    the 100.0 level, price repeatedly tests ~99.9 but never breaks much
    below, and each candle closes back up near the top of its range —
    a textbook seller-absorption footprint.
    """
    candles = []
    for i in range(3):
        fp = {
            99.90: _node(99.90, bid=800, ask=100),   # heavy aggressive selling at the defended low
            99.95: _node(99.95, bid=200, ask=150),
            100.05: _node(100.05, bid=50, ask=300),  # buyers stepping back in higher up
        }
        candles.append(_candle(i, open_=100.0, high=100.1, low=99.90, close=100.05, footprint=fp))
    return candles


def _buyer_absorption_candles(location=100.0):
    candles = []
    for i in range(3):
        fp = {
            100.10: _node(100.10, bid=100, ask=800),  # heavy aggressive buying at the defended high
            100.05: _node(100.05, bid=150, ask=200),
            99.95: _node(99.95, bid=300, ask=50),
        }
        candles.append(_candle(i, open_=100.0, high=100.10, low=99.95, close=99.97, footprint=fp))
    return candles


def test_seller_absorption_detected_with_strong_pattern():
    result = detect_seller_absorption(_seller_absorption_candles(), location_price=100.0)
    assert result.detected is True
    assert result.direction == "SELLER_ABSORPTION"
    assert result.strength > 0
    assert result.defended_price == 99.90
    assert result.repeated_tests == 3


def test_buyer_absorption_detected_with_strong_pattern():
    result = detect_buyer_absorption(_buyer_absorption_candles(), location_price=100.0)
    assert result.detected is True
    assert result.direction == "BUYER_ABSORPTION"
    assert result.defended_price == 100.10


def test_no_absorption_when_level_breaks():
    # Same aggressive selling, but price actually breaks well below location.
    candles = []
    for i in range(3):
        fp = {
            98.00: _node(98.00, bid=800, ask=50),
            99.00: _node(99.00, bid=200, ask=100),
        }
        candles.append(_candle(i, open_=100.0, high=100.0, low=98.00, close=98.10, footprint=fp))
    result = detect_seller_absorption(candles, location_price=100.0, max_break_pct=0.005)
    assert result.detected is False
    assert result.direction == "NONE"


def test_no_absorption_when_delta_is_wrong_sign():
    # Positive delta (net buying) near a bullish location — no seller aggression to absorb.
    candles = []
    for i in range(3):
        fp = {99.90: _node(99.90, bid=50, ask=500)}
        candles.append(_candle(i, open_=100.0, high=100.1, low=99.90, close=100.05, footprint=fp))
    result = detect_seller_absorption(candles, location_price=100.0)
    assert result.detected is False


def test_no_absorption_with_insufficient_candles():
    result = detect_seller_absorption(_seller_absorption_candles()[:1], location_price=100.0, min_candles=2)
    assert result.detected is False
    assert result.repeated_tests == 0


def test_no_absorption_when_candles_are_far_from_location():
    candles = _seller_absorption_candles()
    result = detect_seller_absorption(candles, location_price=500.0)
    assert result.detected is False


def test_strength_is_bounded_0_to_100():
    result = detect_seller_absorption(_seller_absorption_candles(), location_price=100.0)
    assert 0.0 <= result.strength <= 100.0


def test_stronger_pattern_scores_higher_than_weak_pattern():
    strong = detect_seller_absorption(_seller_absorption_candles(), location_price=100.0)

    # Weak pattern: only 2 repeated tests, less concentrated volume, weaker rejection close.
    weak_candles = []
    for i in range(2):
        fp = {99.90: _node(99.90, bid=210, ask=200), 100.0: _node(100.0, bid=100, ask=100)}
        weak_candles.append(_candle(i, open_=100.0, high=100.05, low=99.90, close=99.95, footprint=fp))
    weak = detect_seller_absorption(weak_candles, location_price=100.0)

    assert strong.strength > weak.strength


def test_delta_history_z_score_path_used_when_history_provided():
    history = [10.0, -20.0, 5.0, -15.0, 0.0, 8.0]  # mean small, some spread
    result = detect_seller_absorption(
        _seller_absorption_candles(), location_price=100.0, delta_history=history,
    )
    assert "delta" in result.components
    assert 0.0 <= result.components["delta"] <= 100.0


def test_volume_history_path_used_when_history_provided():
    history = [100.0, 120.0, 90.0, 110.0, 95.0]
    result = detect_seller_absorption(
        _seller_absorption_candles(), location_price=100.0, volume_history=history,
    )
    assert "aggressive_volume" in result.components
