"""Volatility risk premium: VRP = implied vol - forecast realized vol
(Carr & Wu (2009), "Variance Risk Premiums", Review of Financial Studies,
22(3), 1311-1341 — cited alongside Bloch (2016) as the academic backbone
for this signal). Combines svi.svi_atm_iv (the implied side) with
realized_vol.forecast_annualized_vol_from_closes (the forecast side).

A positive VRP means the market is pricing more variance than the model
expects to realize — the textbook "sell volatility" condition, but not a
mechanical signal on its own: see the event-risk / jump-risk caveats
already discussed for this strategy. This module only computes the
number and its Z-score against recent history; it doesn't decide when
that's tradeable.
"""

from typing import List, Optional, Sequence


def compute_vrp(implied_vol: float, forecast_vol: float) -> float:
    """VRP in vol points (not variance) — easier to read directly against
    the IV numbers already shown elsewhere in this package.
    """
    return implied_vol - forecast_vol


def vrp_zscore(current_vrp: float, history: Sequence[float]) -> Optional[float]:
    """Standardizes today's VRP against its own recent history. Returns
    None with fewer than 2 history points (no meaningful std dev) or a
    zero-variance history (every past reading identical).
    """
    if len(history) < 2:
        return None

    n = len(history)
    mean = sum(history) / n
    variance = sum((h - mean) ** 2 for h in history) / n
    std = variance ** 0.5
    if std == 0.0:
        return None
    return (current_vrp - mean) / std


def classify_vrp(
    z_score: Optional[float], rich_threshold: float = 1.0, cheap_threshold: float = -1.0
) -> str:
    """IV_RICH: implied vol is unusually high relative to the forecast
    (favours selling volatility). IV_CHEAP: unusually low (favours buying).
    NEUTRAL/UNKNOWN otherwise or without enough history to say.
    """
    if z_score is None:
        return "UNKNOWN"
    if z_score >= rich_threshold:
        return "IV_RICH"
    if z_score <= cheap_threshold:
        return "IV_CHEAP"
    return "NEUTRAL"


def vrp_signal(classification: str) -> str:
    if classification == "IV_RICH":
        return "SELL_VOLATILITY"
    if classification == "IV_CHEAP":
        return "BUY_VOLATILITY"
    return "NONE"
