from datetime import datetime

import pytest

from backend.app.engines.greeks import BlackScholes
from backend.app.models.greeks import OptionType
from backend.app.strategies.cas_dislocation.analysis import (
    classify_signal,
    compute_dislocation_pct,
    compute_future_displacement,
    compute_future_velocity,
    compute_score,
    compute_spread_quality,
    compute_volume_acceleration,
    is_volatility_shock,
    theoretical_price,
    time_to_expiry_years,
)


# --------------------------- time_to_expiry_years ---------------------------

def test_time_to_expiry_years_15_minutes_before_close():
    now = datetime(2026, 8, 18, 15, 15, 0)
    tau = time_to_expiry_years("2026-08-18", now)
    expected_seconds = 15 * 60  # 15:15 -> 15:30
    assert tau == pytest.approx(expected_seconds / (365 * 24 * 3600), rel=1e-6)


def test_time_to_expiry_years_floors_at_one_second_past_settlement():
    now = datetime(2026, 8, 18, 15, 31, 0)
    tau = time_to_expiry_years("2026-08-18", now)
    assert tau == pytest.approx(1.0 / (365 * 24 * 3600))


# --------------------------- theoretical_price ---------------------------

def test_theoretical_price_matches_black_scholes_directly():
    bs = BlackScholes(risk_free_rate=0.0)
    expected = bs.price(S=24850.0, K=24800.0, T=0.0001, sigma=0.15, option_type=OptionType.CALL)
    actual = theoretical_price(future_price=24850.0, strike=24800.0, tau_years=0.0001, iv=0.15, option_type="CE")
    assert actual == pytest.approx(expected)


def test_theoretical_price_put_matches_black_scholes_directly():
    bs = BlackScholes(risk_free_rate=0.0)
    expected = bs.price(S=24850.0, K=24800.0, T=0.0001, sigma=0.15, option_type=OptionType.PUT)
    actual = theoretical_price(future_price=24850.0, strike=24800.0, tau_years=0.0001, iv=0.15, option_type="PE")
    assert actual == pytest.approx(expected)


# --------------------------- displacement / velocity ---------------------------

def test_compute_future_displacement():
    assert compute_future_displacement(frozen_spot=78020.0, future_price=78090.0) == pytest.approx(70.0)


def test_compute_future_velocity_known_slope():
    history = [(100.0, 78020.0), (101.0, 78055.0), (102.0, 78090.0)]
    velocity = compute_future_velocity(history)
    # (78090 - 78020) / (102 - 100) = 35 pts/sec
    assert velocity == pytest.approx(35.0)


def test_compute_future_velocity_none_with_one_sample():
    assert compute_future_velocity([(100.0, 78020.0)]) is None


def test_compute_future_velocity_ignores_samples_outside_window():
    history = [(0.0, 77000.0), (100.0, 78020.0), (101.0, 78055.0)]
    velocity = compute_future_velocity(history, window_seconds=10.0)
    # Only the last two samples fall inside the 10s window.
    assert velocity == pytest.approx(35.0)


# --------------------------- dislocation ---------------------------

def test_compute_dislocation_pct_underpriced_option():
    # theoretical 84, executable ask 66 -> (84-66)/84 ~ 21.4%
    assert compute_dislocation_pct(84.0, 66.0) == pytest.approx((84 - 66) / 84)


def test_compute_dislocation_pct_overpriced_option_is_negative():
    # theoretical 4, executable ask 9 -> negative, i.e. NOT a buy
    assert compute_dislocation_pct(4.0, 9.0) == pytest.approx((4 - 9) / 4)
    assert compute_dislocation_pct(4.0, 9.0) < 0


def test_compute_dislocation_pct_none_without_executable_price():
    assert compute_dislocation_pct(84.0, None) is None


def test_compute_dislocation_pct_none_with_non_positive_theoretical():
    assert compute_dislocation_pct(0.0, 5.0) is None


# --------------------------- volatility shock ---------------------------

def test_is_volatility_shock_both_sides_surge_from_baseline():
    # The exact story that motivated this engine: CE 3->80, PE 3->80.
    assert is_volatility_shock(ce_current=80.0, ce_baseline=3.0, pe_current=80.0, pe_baseline=3.0) is True


def test_is_volatility_shock_false_for_normal_directional_move():
    # A genuine bullish futures move: CE up, PE down — not a shock.
    assert is_volatility_shock(ce_current=66.0, ce_baseline=20.0, pe_current=9.0, pe_baseline=25.0) is False


def test_is_volatility_shock_false_when_only_one_side_surges():
    assert is_volatility_shock(ce_current=80.0, ce_baseline=3.0, pe_current=10.0, pe_baseline=9.0) is False


def test_is_volatility_shock_false_with_missing_baseline():
    assert is_volatility_shock(ce_current=80.0, ce_baseline=None, pe_current=80.0, pe_baseline=3.0) is False


# --------------------------- spread / volume ---------------------------

def test_compute_spread_quality_tight_spread_scores_high():
    quality = compute_spread_quality(bid=78.0, ask=79.0)  # ~1.3% spread
    assert quality > 0.9


def test_compute_spread_quality_wide_spread_scores_low():
    quality = compute_spread_quality(bid=2.0, ask=85.0)  # huge spread relative to mid
    assert quality < 0.1


def test_compute_spread_quality_none_without_both_sides():
    assert compute_spread_quality(None, 85.0) is None
    assert compute_spread_quality(2.0, None) is None


def test_compute_volume_acceleration_ratio():
    assert compute_volume_acceleration(recent_volume_delta=500.0, baseline_volume_rate=100.0) == pytest.approx(5.0)


def test_compute_volume_acceleration_none_with_zero_baseline():
    assert compute_volume_acceleration(500.0, 0.0) is None


# --------------------------- score ---------------------------

def test_compute_score_all_none_is_zero():
    assert compute_score(None, None, None, None, None, None, None) == 0


def test_compute_score_maxed_inputs_is_100():
    score = compute_score(
        future_displacement=1000.0,       # far past the scale
        future_velocity=1000.0,
        ce_dislocation_pct=5.0,
        pe_dislocation_pct=None,
        ce_spread_quality=1.0,
        pe_spread_quality=None,
        volume_acceleration=1000.0,
    )
    assert score == 100


def test_compute_score_increases_with_dislocation_magnitude():
    low = compute_score(50.0, 5.0, 0.05, None, 0.8, None, 2.0)
    high = compute_score(50.0, 5.0, 0.50, None, 0.8, None, 2.0)
    assert high > low


# --------------------------- classify_signal ---------------------------

def test_classify_signal_shock_always_none():
    assert classify_signal(0.9, 0.9, shock=True) == "NONE"


def test_classify_signal_buy_ce_when_ce_more_underpriced():
    # Replays the worked example: CE theoretical 84 vs ask 66 (~21.4%
    # underpriced) vs PE theoretical 4 vs ask 9 (overpriced, negative).
    ce_pct = compute_dislocation_pct(84.0, 66.0)
    pe_pct = compute_dislocation_pct(4.0, 9.0)
    assert classify_signal(ce_pct, pe_pct, shock=False) == "BUY_CE"


def test_classify_signal_buy_pe_when_pe_more_underpriced():
    assert classify_signal(0.05, 0.30, shock=False) == "BUY_PE"


def test_classify_signal_none_below_minimum_threshold():
    assert classify_signal(0.05, 0.02, shock=False, min_dislocation_pct=0.15) == "NONE"


def test_classify_signal_none_with_missing_data():
    assert classify_signal(None, None, shock=False) == "NONE"
