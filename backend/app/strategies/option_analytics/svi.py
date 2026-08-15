"""Raw SVI implied-volatility-surface fitting (Gatheral 2004), as referenced
in Bloch, D. (2016) "A Practical Guide to Quantitative Volatility Trading",
SSRN 2715517, Section 6.1.2.2 (p.184).

Fits one smile (fixed expiry) at a time:

    w(x) = a + b * (rho * (x - m) + sqrt((x - m)**2 + sigma**2))

where x = ln(K/F) is log-forward-moneyness and w = sigma_BS(K)**2 * tau is
the total implied variance. Total variance, not the vol itself, is the
quantity that behaves smoothly enough to least-squares fit across strikes.

This turns a noisy per-strike IV column from the live NSE chain into five
stable numbers per expiry (a, b, rho, m, sigma), from which ATM vol, skew
and the no-arbitrage check are read off directly — instead of reading raw
IV at a couple of strikes and hoping they're not outliers.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Tuple

import numpy as np
import pytz
from scipy.optimize import least_squares

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")
MIN_TAU_YEARS = 1 / 365  # floor for expiry-day chains, avoids division by ~0


@dataclass
class SviParams:
    a: float
    b: float
    rho: float
    m: float
    sigma: float


def svi_total_variance(params: SviParams, x: np.ndarray) -> np.ndarray:
    """Raw SVI parametrisation of total variance w(x) at log-moneyness x."""
    return params.a + params.b * (
        params.rho * (x - params.m) + np.sqrt((x - params.m) ** 2 + params.sigma ** 2)
    )


def is_arbitrage_free(params: SviParams) -> bool:
    """Gatheral's necessary butterfly-arbitrage condition: the total
    variance curve's minimum, a + b*sigma*sqrt(1-rho**2), must stay
    non-negative. Necessary, not sufficient — see Roper [2010] — but cheap
    to check and catches the common failure mode of a bad fit.
    """
    if params.b < 0 or abs(params.rho) >= 1 or params.sigma <= 0:
        return False
    return params.a + params.b * params.sigma * np.sqrt(1 - params.rho ** 2) >= -1e-8


def time_to_expiry_years(chain: List[Dict[str, Any]]) -> float:
    """Years to expiry from each row's real `expiry` field (Upstox includes
    it per-strike), against today's IST date. Floored at MIN_TAU_YEARS so
    an expiry-day chain doesn't blow up the tau division in svi_iv.
    """
    expiry_str = chain[0]["expiry"]
    expiry = date.fromisoformat(expiry_str)
    today = datetime.now(IST).date()
    days = (expiry - today).days
    return max(days / 365.0, MIN_TAU_YEARS)


def synthetic_forward(chain: List[Dict[str, Any]], spot: float) -> float:
    """Forward price via put-call parity (F = K + C - P) at the strike
    closest to spot. Ignores discounting over the few weeks to a typical
    NSE weekly/monthly expiry — r*T is a few basis points, swamped by
    index option bid/ask noise at that horizon.
    """
    closest = min(chain, key=lambda r: abs(r["strike_price"] - spot))
    call_ltp = closest.get("call_options", {}).get("market_data", {}).get("ltp")
    put_ltp = closest.get("put_options", {}).get("market_data", {}).get("ltp")
    if call_ltp is None or put_ltp is None:
        return spot
    return closest["strike_price"] + (call_ltp - put_ltp)


def extract_smile(
    chain: List[Dict[str, Any]], forward: float, tau: float
) -> Tuple[np.ndarray, np.ndarray]:
    """Pull (log-moneyness, total variance) points from every strike with a
    usable IV, one point per strike (mean of call/put IV where both sides
    are valid — deep OTM legs often only have one side quoted).

    IV from the chain is in vol points (e.g. 12.5 meaning 12.5%), matching
    the convention already used by analysis.extract_atm_iv in this package.
    """
    xs, ws = [], []
    for row in chain:
        strike = row["strike_price"]
        call_iv = row.get("call_options", {}).get("option_greeks", {}).get("iv")
        put_iv = row.get("put_options", {}).get("option_greeks", {}).get("iv")
        ivs = [iv / 100.0 for iv in (call_iv, put_iv) if iv is not None and iv > 0.0]
        if not ivs:
            continue
        iv = sum(ivs) / len(ivs)
        xs.append(np.log(strike / forward))
        ws.append((iv ** 2) * tau)
    return np.array(xs), np.array(ws)


def fit_svi(x: np.ndarray, w: np.ndarray) -> SviParams:
    """Least-squares fit of the raw SVI curve to one expiry's smile.

    SVI fits are prone to local minima (Zeliade Systems 2009), but this
    start (variance floor for a, ATM centring for m, spread of x for sigma)
    is close enough for a single NSE index expiry's handful of strikes —
    no exotic double-humped smile to worry about.
    """
    if len(x) < 5:
        raise ValueError("Need at least 5 strikes with valid IV to fit SVI.")

    a0 = max(w.min() * 0.9, 1e-6)
    b0 = 0.1
    rho0 = 0.0
    m0 = 0.0
    sigma0 = max(float(np.std(x)), 0.05)

    def residuals(p):
        params = SviParams(a=p[0], b=p[1], rho=p[2], m=p[3], sigma=p[4])
        return svi_total_variance(params, x) - w

    lower = [0.0, 0.0, -0.999, -1.0, 1e-4]
    upper = [np.inf, np.inf, 0.999, 1.0, np.inf]

    result = least_squares(
        residuals,
        x0=[a0, b0, rho0, m0, sigma0],
        bounds=(lower, upper),
        method="trf",
    )
    params = SviParams(*result.x)

    if not is_arbitrage_free(params):
        logger.warning(
            "SVI fit violates the Gatheral no-butterfly-arbitrage condition "
            "(a=%.5f b=%.5f rho=%.3f sigma=%.5f) — use with caution.",
            params.a, params.b, params.rho, params.sigma,
        )
    return params


def svi_iv(params: SviParams, x: float, tau: float) -> float:
    """Implied vol at log-moneyness x, backed out from fitted total variance."""
    w = svi_total_variance(params, np.array([x]))[0]
    return float(np.sqrt(max(w, 0.0) / tau))


def svi_atm_iv(params: SviParams, tau: float) -> float:
    return svi_iv(params, 0.0, tau)


def svi_skew_proxy(params: SviParams, tau: float, offset: float = 0.1) -> float:
    """Put IV minus call IV at +/-`offset` log-moneyness — a fixed-moneyness
    skew proxy, not a true delta-25 skew (that needs the BS delta inversion),
    but stable and cheap to read off the fitted curve.
    """
    return svi_iv(params, -offset, tau) - svi_iv(params, offset, tau)
