import numpy as np
import pytest

from backend.app.strategies.option_analytics.dispersion import (
    gamma_hedge_scale,
    implied_correlation_exact,
    implied_correlation_proxy,
    realized_correlation,
    select_dispersion_basket,
    vega_hedge_scale,
)


# --------------------------- implied correlation ---------------------------

def test_implied_correlation_exact_recovers_known_rho():
    """Build an index vol from the Markowitz identity at a known rho, then
    solve for it back out — the real check, since eq 7.6.22 is an exact
    algebraic identity once vols/weights are fixed.
    """
    weights = [0.5, 0.3, 0.2]
    vols = [0.20, 0.25, 0.30]
    true_rho = 0.6

    diag = sum(w * w * s * s for w, s in zip(weights, vols))
    cross = sum(
        weights[i] * weights[j] * vols[i] * vols[j]
        for i in range(3) for j in range(i + 1, 3)
    )
    index_vol_sq = diag + 2 * true_rho * cross
    index_vol = index_vol_sq ** 0.5

    rho = implied_correlation_exact(index_vol, vols, weights)
    assert rho == pytest.approx(true_rho, abs=1e-9)


def test_implied_correlation_exact_rejects_single_constituent():
    with pytest.raises(ValueError):
        implied_correlation_exact(0.2, [0.2], [1.0])


def test_implied_correlation_proxy_matches_exact_when_diagonal_negligible():
    """Bossu's proxy (eq 7.6.23) drops sum(w_i^2 sigma_i^2) as negligible —
    valid for a large, low-weight-concentration basket. With 30 equal-weight
    names the diagonal term really is small relative to the cross term, so
    the two formulas should nearly agree.
    """
    n = 30
    weights = [1.0 / n] * n
    vols = [0.20] * n
    true_rho = 0.5

    diag = sum(w * w * s * s for w, s in zip(weights, vols))
    cross = sum(
        weights[i] * weights[j] * vols[i] * vols[j]
        for i in range(n) for j in range(i + 1, n)
    )
    index_vol = (diag + 2 * true_rho * cross) ** 0.5

    exact = implied_correlation_exact(index_vol, vols, weights)
    proxy = implied_correlation_proxy(index_vol, vols, weights)
    assert proxy == pytest.approx(exact, rel=0.05)


# --------------------------- realized correlation ---------------------------

def test_realized_correlation_perfectly_correlated_series():
    returns = [[0.01, -0.02, 0.03, -0.01, 0.02], [0.02, -0.04, 0.06, -0.02, 0.04]]
    weights = [0.6, 0.4]
    rho = realized_correlation(returns, weights)
    assert rho == pytest.approx(1.0, abs=1e-9)


def test_realized_correlation_uncorrelated_orthogonal_series():
    rng = np.random.default_rng(42)
    a = rng.normal(size=5000)
    b = rng.normal(size=5000)
    rho = realized_correlation([a, b], [0.5, 0.5])
    assert abs(rho) < 0.05


def test_realized_correlation_rejects_single_series():
    with pytest.raises(ValueError):
        realized_correlation([[0.01, 0.02]], [1.0])


# --------------------------- basket selection ---------------------------

def test_select_dispersion_basket_stops_at_target_weight():
    constituents = [
        {"symbol": "A", "weight": 0.15, "oi": 1000},
        {"symbol": "B", "weight": 0.12, "oi": 1000},
        {"symbol": "C", "weight": 0.10, "oi": 1000},
        {"symbol": "D", "weight": 0.05, "oi": 1000},
    ]
    selected = select_dispersion_basket(constituents, target_weight_fraction=0.35)
    # A (0.15) + B (0.12) = 0.27 < 0.35, + C (0.10) = 0.37 >= 0.35, stop
    assert [c["symbol"] for c in selected] == ["A", "B", "C"]


def test_select_dispersion_basket_filters_illiquid_names():
    constituents = [
        {"symbol": "A", "weight": 0.20, "oi": 500},   # illiquid, filtered
        {"symbol": "B", "weight": 0.10, "oi": 50000},
    ]
    selected = select_dispersion_basket(constituents, target_weight_fraction=0.05, min_oi=1000)
    assert [c["symbol"] for c in selected] == ["B"]


# --------------------------- Greek-weighting schemes ---------------------------

def test_vega_hedge_scale_matches_index_vega():
    index_vega = 1000.0
    weights = [0.5, 0.3, 0.2]
    vegas = [200.0, 150.0, 100.0]

    k = vega_hedge_scale(index_vega, vegas, weights)
    total = sum(k * w * v for w, v in zip(weights, vegas))
    assert total == pytest.approx(index_vega)


def test_gamma_hedge_scale_matches_index_gamma():
    index_gamma = 0.05
    weights = [0.5, 0.3, 0.2]
    gammas = [0.01, 0.02, 0.03]

    k = gamma_hedge_scale(index_gamma, gammas, weights)
    total = sum(k * w * g for w, g in zip(weights, gammas))
    assert total == pytest.approx(index_gamma)


def test_vega_hedge_scale_rejects_zero_weighted_vega():
    with pytest.raises(ValueError):
        vega_hedge_scale(1000.0, [0.0, 0.0], [0.5, 0.5])
