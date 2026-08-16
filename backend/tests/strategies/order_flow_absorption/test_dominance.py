from datetime import datetime, timedelta, timezone

from backend.app.order_flow.footprint_candle import FootprintCandle
from backend.app.order_flow.models import FootprintNode
from backend.app.strategies.order_flow_absorption.dominance import (
    evaluate_bullish_dominance, evaluate_bearish_dominance,
    _has_ask_side_imbalance, _has_bid_side_imbalance,
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


# --------------------------- imbalance helpers ---------------------------

def test_has_ask_side_imbalance_true_when_ratio_met():
    fp = {100.0: _node(100.0, bid=10, ask=0), 100.05: _node(100.05, bid=0, ask=45)}
    assert _has_ask_side_imbalance(fp, ratio_pct=400.0) is True  # 45 >= 4x*10


def test_has_ask_side_imbalance_false_when_ratio_not_met():
    fp = {100.0: _node(100.0, bid=10, ask=0), 100.05: _node(100.05, bid=0, ask=30)}
    assert _has_ask_side_imbalance(fp, ratio_pct=400.0) is False


def test_has_bid_side_imbalance_mirrors_ask_side():
    fp = {100.0: _node(100.0, bid=0, ask=10), 100.05: _node(100.05, bid=45, ask=0)}
    assert _has_bid_side_imbalance(fp, ratio_pct=400.0) is True


# --------------------------- bullish dominance ---------------------------

def _absorption_candles():
    return [_candle(0, 100.0, 100.10, 99.90, 100.0, {99.90: _node(99.90, 500, 100)})]


def test_bullish_dominance_confirmed_with_all_three_conditions():
    absorption = _absorption_candles()
    confirmation = [
        _candle(1, 100.0, 100.20, 99.95, 100.15, {
            100.10: _node(100.10, bid=10, ask=5),
            100.15: _node(100.15, bid=0, ask=50),  # 50 >= 4x*10 -> ask-side imbalance
        }),
    ]
    result = evaluate_bullish_dominance(absorption, confirmation, imbalance_ratio_pct=400.0)
    assert result.confirmed is True
    assert result.direction == "BUYER_DOMINANCE"
    assert result.opposing_aggression is True
    assert result.imbalance_confirmed is True
    assert result.microstructure_break is True  # 100.20 > absorption high 100.10


def test_bullish_dominance_fails_without_opposing_aggression():
    absorption = _absorption_candles()
    # negative delta (still net selling) despite touching a new high
    confirmation = [_candle(1, 100.0, 100.20, 99.95, 99.96, {100.0: _node(100.0, bid=50, ask=10)})]
    result = evaluate_bullish_dominance(absorption, confirmation)
    assert result.confirmed is False
    assert result.opposing_aggression is False


def test_bullish_dominance_fails_without_imbalance():
    absorption = _absorption_candles()
    confirmation = [_candle(1, 100.0, 100.20, 99.95, 100.15, {100.0: _node(100.0, bid=20, ask=25)})]  # weak ratio
    result = evaluate_bullish_dominance(absorption, confirmation, imbalance_ratio_pct=400.0)
    assert result.confirmed is False
    assert result.imbalance_confirmed is False


def test_bullish_dominance_fails_without_microstructure_break():
    absorption = _absorption_candles()  # high = 100.10
    confirmation = [_candle(1, 100.0, 100.05, 99.95, 100.02, {99.95: _node(99.95, bid=5, ask=50)})]  # never exceeds 100.10
    result = evaluate_bullish_dominance(absorption, confirmation)
    assert result.confirmed is False
    assert result.microstructure_break is False


def test_bullish_dominance_no_confirmation_candles_returns_none():
    result = evaluate_bullish_dominance(_absorption_candles(), [])
    assert result.confirmed is False
    assert result.direction == "NONE"


# --------------------------- bearish dominance (mirror) ---------------------------

def _bearish_absorption_candles():
    return [_candle(0, 100.0, 100.10, 99.90, 100.0, {100.10: _node(100.10, bid=100, ask=500)})]


def test_bearish_dominance_confirmed_with_all_three_conditions():
    absorption = _bearish_absorption_candles()
    confirmation = [
        _candle(1, 100.0, 100.05, 99.80, 99.85, {
            99.80: _node(99.80, bid=0, ask=10),   # resting ask interest at the lower level
            99.85: _node(99.85, bid=50, ask=0),   # 50 >= 4x*10 -> aggressive selling dwarfs it: bid-side imbalance
        }),
    ]
    result = evaluate_bearish_dominance(absorption, confirmation, imbalance_ratio_pct=400.0)
    assert result.confirmed is True
    assert result.direction == "SELLER_DOMINANCE"
    assert result.microstructure_break is True  # 99.80 < absorption low 99.90


def test_bearish_dominance_fails_without_opposing_aggression():
    absorption = _bearish_absorption_candles()
    confirmation = [_candle(1, 100.0, 100.05, 99.80, 99.95, {100.0: _node(100.0, bid=10, ask=50)})]  # net buying still
    result = evaluate_bearish_dominance(absorption, confirmation)
    assert result.confirmed is False


def test_configurable_ratio_thresholds():
    fp = {100.0: _node(100.0, bid=10, ask=0), 100.05: _node(100.05, bid=0, ask=25)}
    # 25 >= 2x*10 (200%) but not >= 3x*10 (300%)
    assert _has_ask_side_imbalance(fp, ratio_pct=200.0) is True
    assert _has_ask_side_imbalance(fp, ratio_pct=300.0) is False
