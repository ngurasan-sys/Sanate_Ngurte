import pytest

from backend.app.strategies.option_analytics.vrp import (
    classify_vrp,
    compute_vrp,
    vrp_signal,
    vrp_zscore,
)


def test_compute_vrp_positive_when_implied_richer():
    assert compute_vrp(implied_vol=0.20, forecast_vol=0.15) == pytest.approx(0.05)


def test_compute_vrp_negative_when_implied_cheaper():
    assert compute_vrp(implied_vol=0.10, forecast_vol=0.15) == pytest.approx(-0.05)


def test_vrp_zscore_none_with_insufficient_history():
    assert vrp_zscore(0.05, []) is None
    assert vrp_zscore(0.05, [0.03]) is None


def test_vrp_zscore_none_with_zero_variance_history():
    assert vrp_zscore(0.05, [0.03, 0.03, 0.03]) is None


def test_vrp_zscore_matches_manual_calculation():
    history = [0.01, 0.02, 0.03, 0.04, 0.05]
    current = 0.09
    mean = sum(history) / len(history)
    variance = sum((h - mean) ** 2 for h in history) / len(history)
    std = variance ** 0.5
    expected = (current - mean) / std
    assert vrp_zscore(current, history) == pytest.approx(expected)


def test_classify_vrp_thresholds():
    assert classify_vrp(None) == "UNKNOWN"
    assert classify_vrp(1.5) == "IV_RICH"
    assert classify_vrp(-1.5) == "IV_CHEAP"
    assert classify_vrp(0.2) == "NEUTRAL"
    assert classify_vrp(1.0) == "IV_RICH"  # boundary is inclusive
    assert classify_vrp(-1.0) == "IV_CHEAP"


def test_vrp_signal_mapping():
    assert vrp_signal("IV_RICH") == "SELL_VOLATILITY"
    assert vrp_signal("IV_CHEAP") == "BUY_VOLATILITY"
    assert vrp_signal("NEUTRAL") == "NONE"
    assert vrp_signal("UNKNOWN") == "NONE"
