from backend.app.strategies.order_flow_absorption.fibonacci import compute_retracement_levels
from backend.app.strategies.order_flow_absorption.location import evaluate_location
from backend.app.strategies.order_flow_absorption.volume_profile import VolumeProfile


def profile(poc=None, vah=None, val=None, hvn=None, lvn=None):
    return VolumeProfile(poc=poc, vah=vah, val=val, hvn=hvn or [], lvn=lvn or [], total_volume=1000)


def test_bullish_location_at_current_val():
    result = evaluate_location(price=100.0, current_profile=profile(poc=105, vah=110, val=100.0))
    assert result.is_bullish_location is True
    assert "current_val" in result.matched_bullish_factors


def test_bearish_location_at_current_vah():
    result = evaluate_location(price=110.0, current_profile=profile(poc=105, vah=110.0, val=100))
    assert result.is_bearish_location is True
    assert "current_vah" in result.matched_bearish_factors


def test_bullish_location_at_previous_day_low():
    result = evaluate_location(price=95.0, previous_day_low=95.0)
    assert result.is_bullish_location is True
    assert "previous_day_low" in result.matched_bullish_factors


def test_bullish_location_at_swing_low():
    result = evaluate_location(price=88.0, swing_low=88.0)
    assert result.is_bullish_location is True


def test_bullish_location_at_fib_discount():
    fib = compute_retracement_levels(200.0, 100.0, "DISCOUNT")
    result = evaluate_location(price=fib.levels[0.786], fib_discount=fib)
    assert result.is_bullish_location is True
    assert "fib_discount" in result.matched_bullish_factors


def test_bearish_location_at_fib_premium():
    fib = compute_retracement_levels(200.0, 100.0, "PREMIUM")
    result = evaluate_location(price=fib.levels[0.786], fib_premium=fib)
    assert result.is_bearish_location is True


def test_vwap_alone_is_never_sufficient():
    result = evaluate_location(price=100.0, vwap=100.0)
    assert result.is_bullish_location is False
    assert result.is_bearish_location is False
    assert "vwap" in result.matched_bullish_factors  # noted, but doesn't carry the location


def test_vwap_confluence_joins_a_real_factor():
    result = evaluate_location(price=95.0, previous_day_low=95.0, vwap=95.0)
    assert result.is_bullish_location is True
    assert "vwap" in result.matched_bullish_factors
    assert "previous_day_low" in result.matched_bullish_factors


def test_middle_of_value_forces_no_trade_by_default():
    # price inside value area, not near either edge or POC
    result = evaluate_location(price=105.0, current_profile=profile(poc=112, vah=110, val=100))
    assert result.is_middle_of_value is True
    assert result.is_bullish_location is False
    assert result.is_bearish_location is False


def test_middle_of_value_override_allows_a_matched_factor_through():
    result = evaluate_location(
        price=105.0, current_profile=profile(poc=112, vah=110, val=100),
        previous_day_low=105.0,  # matches bullish factor despite being "middle"
        allow_middle_of_value_override=True,
    )
    assert result.is_middle_of_value is True
    assert result.is_bullish_location is True


def test_near_poc_is_always_middle_of_value():
    result = evaluate_location(price=112.0, current_profile=profile(poc=112, vah=130, val=90))
    assert result.is_middle_of_value is True


def test_no_location_when_nothing_matches():
    result = evaluate_location(price=150.0, current_profile=profile(poc=105, vah=110, val=100))
    assert result.is_bullish_location is False
    assert result.is_bearish_location is False
    assert result.is_middle_of_value is False


def test_lvn_counts_as_a_bullish_and_bearish_candidate_factor():
    result = evaluate_location(price=103.0, current_profile=profile(poc=110, vah=120, val=90, lvn=[103.0]))
    # 103 is inside the value area but not near POC/edges except via LVN match — LVN alone triggers bullish factor
    assert "lvn" in result.matched_bullish_factors
