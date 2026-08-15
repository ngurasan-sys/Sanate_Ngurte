"""Model-free implied variance, per Bloch (2016) eq 7.1.1, SSRN 2715517,
p.220 ("A Practical Guide to Quantitative Volatility Trading"):

    Et0[int_0^T |sigma|^2 dt]
        = 2 int_0^F (1/K^2) P(T,K) dK + 2 int_F^infinity (1/K^2) C(T,K) dK

Discretized in the standard CBOE VIX / Britten-Jones-Neuberger (2000) form:

    sigma_MF^2 = (2/tau) e^{r*tau} sum_i (dK_i / K_i^2) Q(K_i)
                 - (1/tau) (F/K_0 - 1)^2

using OTM put prices for strikes below the forward, OTM call prices above
it, and the average of the put/call price at K_0 (the strike at or just
below the forward). This is model-independent — it does not assume
Black-Scholes, it just weights observed option prices directly — so it
gives a cleaner variance signal than any single strike's Black-Scholes IV.
"""

import bisect
import math
from typing import Any, Dict, List, Optional


def _strike_spacing(strikes: List[float], i: int) -> float:
    """Centred difference, one-sided at the ends — the standard CBOE
    treatment of the outermost strikes in the chain.
    """
    if i == 0:
        return strikes[1] - strikes[0]
    if i == len(strikes) - 1:
        return strikes[i] - strikes[i - 1]
    return (strikes[i + 1] - strikes[i - 1]) / 2.0


def model_free_variance(
    chain: List[Dict[str, Any]], forward: float, tau: float, r: float = 0.0
) -> Optional[float]:
    """Annualised model-free variance (sigma_MF^2) for one expiry's chain.

    Returns None when there aren't enough strikes with usable OTM prices
    either side of the forward to make the sum meaningful.
    """
    if tau <= 0:
        return None

    sorted_chain = sorted(chain, key=lambda row: row["strike_price"])
    strikes = [row["strike_price"] for row in sorted_chain]
    if len(strikes) < 4:
        return None

    # K0: the largest strike <= forward — the OTM put/call cutover and the
    # reference strike for the second (correction) term.
    k0_idx = bisect.bisect_right(strikes, forward) - 1
    if k0_idx < 0:
        return None
    k0 = strikes[k0_idx]

    total = 0.0
    for i, row in enumerate(sorted_chain):
        k = row["strike_price"]
        d_k = _strike_spacing(strikes, i)
        if k < k0:
            price = row.get("put_options", {}).get("market_data", {}).get("ltp")
        elif k > k0:
            price = row.get("call_options", {}).get("market_data", {}).get("ltp")
        else:
            call = row.get("call_options", {}).get("market_data", {}).get("ltp")
            put = row.get("put_options", {}).get("market_data", {}).get("ltp")
            if call is None or put is None:
                continue
            price = (call + put) / 2.0
        if price is None or price <= 0 or k <= 0:
            continue
        total += (d_k / (k ** 2)) * price

    if total == 0.0:
        return None

    correction = (1.0 / tau) * ((forward / k0) - 1.0) ** 2
    variance = (2.0 / tau) * math.exp(r * tau) * total - correction
    return max(variance, 0.0)


def model_free_iv(
    chain: List[Dict[str, Any]], forward: float, tau: float, r: float = 0.0
) -> Optional[float]:
    """sqrt of model_free_variance — a single model-free ATM-equivalent IV
    number, comparable directly to a realized-vol forecast for the same
    horizon to build a volatility-risk-premium signal.
    """
    variance = model_free_variance(chain, forward, tau, r)
    if variance is None:
        return None
    return variance ** 0.5
