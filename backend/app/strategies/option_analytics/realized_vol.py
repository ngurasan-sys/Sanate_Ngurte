"""Realized-volatility forecasting from daily close prices — the
"forecast RV" half of the volatility risk premium signal
(VRP = implied vol - forecast realized vol). Not part of Bloch (2016);
that paper covers the implied side (SVI surface, model-free variance) but
leaves realized-vol forecasting to standard time-series literature — this
follows Corsi, F. (2009), "A Simple Approximate Long-Memory Model of
Realized Volatility", Journal of Financial Econometrics, 7(2), 174-196
(the HAR-RV model).

Honest caveat baked into every function here: with only daily close
prices (no intraday data — see historical_candles.py, which only fetches
daily candles), the "realized variance" for a single day is approximated
by that day's squared close-to-close log return. True HAR-RV normally
sums many intraday squared returns per day, which is a much less noisy RV
estimate. This daily-close proxy is the coarsest honest version of the
model, not the textbook one — expect more forecast noise than the
literature's reported accuracy.
"""

from typing import List, Optional, Tuple

import numpy as np


def daily_log_returns(closes: List[float]) -> List[float]:
    return [float(np.log(closes[i] / closes[i - 1])) for i in range(1, len(closes))]


def daily_realized_variance(returns: List[float]) -> List[float]:
    """Single-day RV proxy: that day's squared log return."""
    return [r * r for r in returns]


def historical_volatility(returns: List[float], trading_days: int = 252) -> Optional[float]:
    """Simple close-to-close annualized realized vol over the whole
    window — the naive benchmark HAR-RV is meant to beat.
    """
    if len(returns) < 2:
        return None
    variance = sum(r * r for r in returns) / len(returns)
    return (variance * trading_days) ** 0.5


def ewma_volatility(returns: List[float], lam: float = 0.94, trading_days: int = 252) -> Optional[float]:
    """RiskMetrics-style EWMA vol: lam=0.94 is the standard RiskMetrics
    daily decay factor, not tuned for NSE data — recalibrate if this ships.
    """
    if not returns:
        return None
    variance = returns[0] ** 2
    for r in returns[1:]:
        variance = lam * variance + (1 - lam) * r * r
    return (variance * trading_days) ** 0.5


def _har_rv_features(rv: List[float]) -> Tuple[np.ndarray, np.ndarray]:
    """Build HAR-RV regression samples: X columns are
    [1, RV_daily, RV_weekly(5d avg), RV_monthly(22d avg)], y is RV_{t+1}.
    """
    n = len(rv)
    monthly_window = 22
    xs, ys = [], []
    for t in range(monthly_window - 1, n - 1):
        rv_d = rv[t]
        rv_w = sum(rv[t - 4:t + 1]) / 5
        rv_m = sum(rv[t - monthly_window + 1:t + 1]) / monthly_window
        xs.append([1.0, rv_d, rv_w, rv_m])
        ys.append(rv[t + 1])
    return np.array(xs), np.array(ys)


def har_rv_forecast(rv: List[float], min_regression_rows: int = 5) -> Optional[float]:
    """Corsi (2009) HAR-RV: fit RV_{t+1} = b0 + bd*RV_t + bw*RV_t^(w) +
    bm*RV_t^(m) by OLS on the supplied history, then forecast one step
    ahead from the most recent window. Returns None when there isn't
    enough history for the 22-day window plus a handful of regression rows
    to fit against — the paper's own minimum a HAR-RV fit needs to mean
    anything.
    """
    n = len(rv)
    if n < 22 + min_regression_rows + 1:
        return None

    x, y = _har_rv_features(rv)
    if x.shape[0] < min_regression_rows:
        return None

    coeffs, *_ = np.linalg.lstsq(x, y, rcond=None)
    rv_d = rv[-1]
    rv_w = sum(rv[-5:]) / 5
    rv_m = sum(rv[-22:]) / 22
    forecast = coeffs[0] + coeffs[1] * rv_d + coeffs[2] * rv_w + coeffs[3] * rv_m
    return max(float(forecast), 0.0)


def forecast_annualized_vol_from_closes(
    closes: List[float], trading_days: int = 252
) -> Optional[float]:
    """End-to-end: daily closes -> HAR-RV one-step forecast of tomorrow's
    daily variance -> annualized vol, directly comparable to an implied
    vol number (e.g. svi.svi_atm_iv) for a VRP calculation.
    """
    returns = daily_log_returns(closes)
    rv = daily_realized_variance(returns)
    forecast_daily_var = har_rv_forecast(rv)
    if forecast_daily_var is None:
        return None
    return (forecast_daily_var * trading_days) ** 0.5
