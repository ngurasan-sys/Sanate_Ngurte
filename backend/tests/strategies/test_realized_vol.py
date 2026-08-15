import numpy as np
import pytest

from backend.app.strategies.option_analytics.realized_vol import (
    daily_log_returns,
    daily_realized_variance,
    ewma_volatility,
    forecast_annualized_vol_from_closes,
    har_rv_forecast,
    historical_volatility,
)


def _simulate_closes(sigma_daily: float, n: int, seed: int = 7, start: float = 25000.0):
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.0, scale=sigma_daily, size=n)
    closes = [start]
    for r in returns:
        closes.append(closes[-1] * np.exp(r))
    return closes


def test_daily_log_returns_basic():
    closes = [100.0, 110.0, 99.0]
    returns = daily_log_returns(closes)
    assert returns[0] == pytest.approx(np.log(1.1))
    assert returns[1] == pytest.approx(np.log(99.0 / 110.0))


def test_daily_realized_variance_is_squared_returns():
    returns = [0.01, -0.02, 0.03]
    rv = daily_realized_variance(returns)
    assert rv == pytest.approx([0.0001, 0.0004, 0.0009])


def test_historical_volatility_recovers_known_sigma():
    sigma_daily = 0.20 / (252 ** 0.5)  # 20% annualized
    closes = _simulate_closes(sigma_daily, n=2000, seed=1)
    returns = daily_log_returns(closes)
    vol = historical_volatility(returns)
    assert vol == pytest.approx(0.20, rel=0.05)


def test_historical_volatility_none_with_too_few_returns():
    assert historical_volatility([0.01]) is None
    assert historical_volatility([]) is None


def test_ewma_volatility_recovers_known_sigma():
    sigma_daily = 0.20 / (252 ** 0.5)
    closes = _simulate_closes(sigma_daily, n=2000, seed=2)
    returns = daily_log_returns(closes)
    vol = ewma_volatility(returns)
    assert vol == pytest.approx(0.20, rel=0.15)


def test_ewma_volatility_none_with_empty_returns():
    assert ewma_volatility([]) is None


def test_har_rv_forecast_none_with_too_little_history():
    assert har_rv_forecast([0.0001] * 20) is None


def test_har_rv_forecast_recovers_roughly_the_right_scale():
    """HAR-RV is a statistical forecast, not an exact recovery — check it
    lands in the right ballpark for a stationary-vol series, not that it
    hits the true value precisely.
    """
    sigma_daily = 0.20 / (252 ** 0.5)
    closes = _simulate_closes(sigma_daily, n=500, seed=3)
    returns = daily_log_returns(closes)
    rv = daily_realized_variance(returns)

    forecast_daily_var = har_rv_forecast(rv)
    assert forecast_daily_var is not None
    forecast_annual_vol = (forecast_daily_var * 252) ** 0.5
    assert forecast_annual_vol == pytest.approx(0.20, rel=0.3)


def test_forecast_annualized_vol_from_closes_end_to_end():
    sigma_daily = 0.18 / (252 ** 0.5)
    closes = _simulate_closes(sigma_daily, n=500, seed=4)
    vol = forecast_annualized_vol_from_closes(closes)
    assert vol is not None
    assert vol == pytest.approx(0.18, rel=0.3)


def test_forecast_annualized_vol_from_closes_none_with_too_few_closes():
    assert forecast_annualized_vol_from_closes([25000.0] * 10) is None
