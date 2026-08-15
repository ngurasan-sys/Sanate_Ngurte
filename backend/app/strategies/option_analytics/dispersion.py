"""Dispersion-trading math from Bloch (2016) Section 7.6, SSRN 2715517,
"A Practical Guide to Quantitative Volatility Trading" (p.244-257):
implied correlation (eq 7.6.22 / the Bossu 2006 proxy eq 7.6.23), realized
correlation (eq 7.6.24), basket selection (Section 7.6.2.3, p.249), and the
vega/gamma weighting schemes described there.

Bloch's own caution (Remark 7.6.2, p.246) applies to every function here:
plugging implied volatility into the Markowitz portfolio-variance identity
to back out an "implied correlation" is market convention, not a rigorous
option-pricing-theory relation — no-dominance no longer holds once you mix
a basket option price with a sum of single-name option prices. Treat these
as signals to backtest, not arbitrage-free truths.

Only the vega- and gamma-hedging weighting schemes are implemented — the
paper describes a theta-hedging scheme's *effect* (short vega and short
gamma) without giving its construction, so it is not reproduced here.
"""

from typing import Dict, List, Sequence

import numpy as np


def implied_correlation_exact(
    index_vol: float, constituent_vols: Sequence[float], weights: Sequence[float]
) -> float:
    """Eq 7.6.22: solve the Markowitz portfolio-variance identity

        sigma_I^2 = sum_i w_i^2 sigma_i^2 + 2 rho sum_{i<j} w_i w_j sigma_i sigma_j

    for a single average pairwise correlation rho.
    """
    n = len(weights)
    if n < 2:
        raise ValueError("Need at least two constituents to solve for an implied correlation.")

    diag = sum(w * w * s * s for w, s in zip(weights, constituent_vols))
    cross = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            cross += weights[i] * weights[j] * constituent_vols[i] * constituent_vols[j]

    if cross == 0.0:
        raise ValueError("Cross term is zero — check weights/vols are nonzero.")
    return (index_vol ** 2 - diag) / (2.0 * cross)


def implied_correlation_proxy(
    index_vol: float, constituent_vols: Sequence[float], weights: Sequence[float]
) -> float:
    """Eq 7.6.23 (Bossu 2006): the diagonal term sum(w_i^2 sigma_i^2) is
    dropped as negligible, valid when rho_impl > 0.15 and N > 20 (a large,
    well-diversified basket — NIFTY/BANKNIFTY qualify, a 5-stock sector
    basket does not).

        rho_impl ~= sigma_I^2 / (sum_i w_i sigma_i)^2
    """
    avg = sum(w * s for w, s in zip(weights, constituent_vols))
    if avg == 0.0:
        raise ValueError("Weighted average constituent vol is zero.")
    return (index_vol ** 2) / (avg ** 2)


def realized_correlation(
    returns: Sequence[Sequence[float]], weights: Sequence[float]
) -> float:
    """Eq 7.6.24: weighted average pairwise realized correlation.

    `returns[i]` is stock i's return series — same length and same dates
    across all series, already aligned by the caller.
    """
    n = len(weights)
    if n < 2:
        raise ValueError("Need at least two constituents.")

    arr = np.asarray(returns, dtype=float)
    corr_matrix = np.corrcoef(arr)

    num = 0.0
    denom = 0.0
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            num += weights[i] * weights[j] * corr_matrix[i, j]
            denom += weights[i] * weights[j]

    if denom == 0.0:
        raise ValueError("Sum of pairwise weights is zero.")
    return num / denom


def select_dispersion_basket(
    constituents: List[Dict], target_weight_fraction: float = 0.35, min_oi: float = 0.0
) -> List[Dict]:
    """Section 7.6.2.3 (p.249) market practice: build the long leg from the
    heaviest-weighted, most liquid names, taking them in weight order until
    their combined index weight covers `target_weight_fraction` — the paper
    cites 30-40% of index weight as typical.

    Each item in `constituents`: {"symbol", "weight", "oi", ...}. Returns
    the selected subset, ranked by weight descending.
    """
    liquid = [c for c in constituents if c.get("oi", 0) >= min_oi]
    ranked = sorted(liquid, key=lambda c: c["weight"], reverse=True)

    selected = []
    cumulative = 0.0
    for c in ranked:
        if cumulative >= target_weight_fraction:
            break
        selected.append(c)
        cumulative += c["weight"]
    return selected


def vega_hedge_scale(
    index_vega: float, constituent_vegas: Sequence[float], weights: Sequence[float]
) -> float:
    """Vega-hedging weighting (p.249-250): size each constituent leg so the
    basket's total vega matches the index leg's vega, immunising the trade
    against a uniform short-term move in the general level of volatility.

    Returns the single scale factor k such that
    sum_i (k * weights[i] * constituent_vegas[i]) == index_vega.
    Position size for constituent i is then k * weights[i].
    """
    weighted_vega = sum(w * v for w, v in zip(weights, constituent_vegas))
    if weighted_vega == 0.0:
        raise ValueError("Weighted constituent vega is zero.")
    return index_vega / weighted_vega


def gamma_hedge_scale(
    index_gamma: float, constituent_gammas: Sequence[float], weights: Sequence[float]
) -> float:
    """Gamma-hedging weighting (p.250): same construction as
    vega_hedge_scale but matching gamma instead of vega, immunising the
    trade against a large move in the underlying stocks.
    """
    weighted_gamma = sum(w * g for w, g in zip(weights, constituent_gammas))
    if weighted_gamma == 0.0:
        raise ValueError("Weighted constituent gamma is zero.")
    return index_gamma / weighted_gamma
