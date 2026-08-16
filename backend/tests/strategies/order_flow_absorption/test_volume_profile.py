from datetime import datetime, timezone

from backend.app.order_flow.footprint_candle import FootprintCandle
from backend.app.order_flow.models import FootprintNode
from backend.app.strategies.order_flow_absorption.volume_profile import (
    build_price_volume_distribution, compute_poc, compute_value_area,
    find_hvn_lvn, compute_volume_profile,
)


def _node(price, total_volume):
    return FootprintNode(price=price, bid_volume=total_volume // 2, ask_volume=total_volume - total_volume // 2, total_volume=total_volume)


def _candle(footprint):
    prices = list(footprint.keys())
    return FootprintCandle(
        instrument_key="NIFTY FUT", timeframe="5m", open_time=datetime.now(timezone.utc),
        open=prices[0], high=max(prices), low=min(prices), close=prices[-1],
        footprint=footprint,
    )


def test_build_price_volume_distribution_merges_across_candles():
    c1 = _candle({100.0: _node(100.0, 50), 101.0: _node(101.0, 30)})
    c2 = _candle({100.0: _node(100.0, 20), 102.0: _node(102.0, 10)})
    dist = build_price_volume_distribution([c1, c2])
    assert dist == {100.0: 70, 101.0: 30, 102.0: 10}


def test_compute_poc_is_the_highest_volume_level():
    dist = {100.0: 10, 101.0: 90, 102.0: 5}
    assert compute_poc(dist) == 101.0


def test_compute_poc_empty_distribution_returns_none():
    assert compute_poc({}) is None


def test_compute_value_area_captures_target_pct_around_poc():
    # Total = 100. POC at 101 (50). Expand: above(102)=20 vs below(100)=25 -> below wins first.
    dist = {99.0: 5, 100.0: 25, 101.0: 50, 102.0: 20}
    vah, val = compute_value_area(dist, value_area_pct=0.68)
    # captured starts at 50 (poc). Need >= 68 -> add below(25) -> 75 >= 68 -> stop.
    assert val == 100.0
    assert vah == 101.0


def test_compute_value_area_expands_both_directions_if_needed():
    dist = {98.0: 5, 99.0: 10, 100.0: 10, 101.0: 40, 102.0: 10, 103.0: 5}
    vah, val = compute_value_area(dist, value_area_pct=0.68)
    total = sum(dist.values())
    assert total == 80
    # target = 54.4; poc=101(40); above(102)=10 vs below(100)=10 -> tie, above wins (>=)
    # captured=50, still <54.4 -> next: above(103)=5 vs below(100)=10 -> below wins
    # captured=60 >= 54.4 stop. val=100, vah=102
    assert val == 100.0
    assert vah == 102.0


def test_compute_value_area_empty_returns_none_none():
    assert compute_value_area({}) == (None, None)


def test_find_hvn_lvn_identifies_local_extrema():
    dist = {100.0: 10, 101.0: 50, 102.0: 5, 103.0: 40, 104.0: 8}
    hvn, lvn = find_hvn_lvn(dist)
    assert 101.0 in hvn
    assert 103.0 in hvn
    assert 102.0 in lvn


def test_find_hvn_lvn_endpoints_never_classified():
    dist = {100.0: 100, 101.0: 5, 102.0: 100}
    hvn, lvn = find_hvn_lvn(dist)
    assert 100.0 not in hvn and 100.0 not in lvn
    assert 102.0 not in hvn and 102.0 not in lvn
    assert 101.0 in lvn


def test_compute_volume_profile_end_to_end():
    c1 = _candle({100.0: _node(100.0, 10), 101.0: _node(101.0, 80), 102.0: _node(102.0, 10)})
    profile = compute_volume_profile([c1])
    assert profile.poc == 101.0
    assert profile.total_volume == 100
    assert profile.vah is not None and profile.val is not None


def test_compute_volume_profile_no_candles_returns_empty_profile():
    profile = compute_volume_profile([])
    assert profile.poc is None
    assert profile.vah is None
    assert profile.val is None
    assert profile.hvn == []
    assert profile.total_volume == 0
