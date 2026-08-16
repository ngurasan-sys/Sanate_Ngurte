from datetime import datetime, timezone

from backend.app.order_flow.footprint_candle import FootprintCandle
from backend.app.order_flow.models import FootprintNode
from backend.app.strategies.order_flow_absorption.vwap import compute_session_vwap


def _node(price, total_volume):
    return FootprintNode(price=price, bid_volume=total_volume // 2, ask_volume=total_volume - total_volume // 2, total_volume=total_volume)


def _candle(footprint):
    prices = list(footprint.keys())
    return FootprintCandle(
        instrument_key="NIFTY FUT", timeframe="5m", open_time=datetime.now(timezone.utc),
        open=prices[0], high=max(prices), low=min(prices), close=prices[-1],
        footprint=footprint,
    )


def test_compute_session_vwap_is_volume_weighted():
    candle = _candle({100.0: _node(100.0, 100), 110.0: _node(110.0, 300)})
    # (100*100 + 110*300) / 400 = 107.5
    assert compute_session_vwap([candle]) == 107.5


def test_compute_session_vwap_merges_across_candles():
    c1 = _candle({100.0: _node(100.0, 100)})
    c2 = _candle({200.0: _node(200.0, 100)})
    assert compute_session_vwap([c1, c2]) == 150.0


def test_compute_session_vwap_no_volume_returns_none():
    candle = _candle({100.0: _node(100.0, 0)})
    assert compute_session_vwap([candle]) is None


def test_compute_session_vwap_empty_candles_returns_none():
    assert compute_session_vwap([]) is None
