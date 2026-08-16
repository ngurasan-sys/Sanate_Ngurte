import pytest

from backend.app.strategies.order_flow_absorption.fibonacci import (
    compute_retracement_levels, is_price_in_fib_zone, is_invalidated, closest_level,
)


def test_discount_levels_measured_down_from_swing_high():
    fib = compute_retracement_levels(swing_high=200.0, swing_low=100.0, direction="DISCOUNT")
    # span=100; 70.5% -> 200 - 70.5 = 129.5; 78.6% -> 121.4; 88.6% -> 111.4
    assert fib.levels[0.705] == pytest.approx(129.5)
    assert fib.levels[0.786] == pytest.approx(121.4)
    assert fib.levels[0.886] == pytest.approx(111.4)


def test_premium_levels_measured_up_from_swing_low():
    fib = compute_retracement_levels(swing_high=200.0, swing_low=100.0, direction="PREMIUM")
    assert fib.levels[0.705] == pytest.approx(170.5)
    assert fib.levels[0.786] == pytest.approx(178.6)
    assert fib.levels[0.886] == pytest.approx(188.6)


def test_invalidation_price_defaults_to_88_6_pct():
    fib = compute_retracement_levels(200.0, 100.0, "DISCOUNT")
    assert fib.invalidation_price == pytest.approx(111.4)


def test_rejects_swing_high_not_greater_than_swing_low():
    with pytest.raises(ValueError):
        compute_retracement_levels(100.0, 200.0, "DISCOUNT")
    with pytest.raises(ValueError):
        compute_retracement_levels(100.0, 100.0, "DISCOUNT")


def test_rejects_unknown_direction():
    with pytest.raises(ValueError):
        compute_retracement_levels(200.0, 100.0, "SIDEWAYS")


def test_is_price_in_fib_zone_true_near_a_level():
    fib = compute_retracement_levels(200.0, 100.0, "DISCOUNT")
    assert is_price_in_fib_zone(121.4, fib) is True
    assert is_price_in_fib_zone(121.45, fib, tolerance_pct=0.001) is True  # within 0.1% of span


def test_is_price_in_fib_zone_false_far_from_any_level():
    fib = compute_retracement_levels(200.0, 100.0, "DISCOUNT")
    assert is_price_in_fib_zone(150.0, fib) is False


def test_is_invalidated_discount_when_price_trades_below_invalidation():
    fib = compute_retracement_levels(200.0, 100.0, "DISCOUNT")
    assert is_invalidated(110.0, fib) is True
    assert is_invalidated(115.0, fib) is False


def test_is_invalidated_premium_when_price_trades_above_invalidation():
    fib = compute_retracement_levels(200.0, 100.0, "PREMIUM")
    assert is_invalidated(190.0, fib) is True
    assert is_invalidated(185.0, fib) is False


def test_closest_level_finds_nearest_configured_pct():
    fib = compute_retracement_levels(200.0, 100.0, "DISCOUNT")
    assert closest_level(120.0, fib) == 0.786  # 121.4 is closest to 120


def test_closest_level_empty_levels_returns_none():
    fib = compute_retracement_levels(200.0, 100.0, "DISCOUNT", levels=())
    assert closest_level(120.0, fib) is None
