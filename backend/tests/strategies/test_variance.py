import pytest

from backend.app.engines.greeks import BlackScholes
from backend.app.models.greeks import OptionType
from backend.app.strategies.option_analytics.variance import (
    model_free_iv,
    model_free_variance,
)


def _bs_chain(spot, forward, strikes, sigma, tau, r=0.0):
    """A synthetic chain priced exactly off Black-Scholes at a single flat
    vol — the real reference case the model-free discretization must
    recover, per Britten-Jones & Neuberger (2000) / the CBOE VIX white
    paper: with dense enough strikes it converges tightly to sigma**2.
    """
    bs = BlackScholes(risk_free_rate=r)
    rows = []
    for k in strikes:
        call = bs.price(forward, k, tau, sigma, OptionType.CALL)
        put = bs.price(forward, k, tau, sigma, OptionType.PUT)
        rows.append({
            "strike_price": k,
            "call_options": {"market_data": {"ltp": call}},
            "put_options": {"market_data": {"ltp": put}},
        })
    return rows


def test_model_free_variance_recovers_flat_bs_vol():
    sigma = 0.20
    tau = 30 / 365
    forward = 25000.0
    # +/-16% of forward: needed for the tails to actually converge at this
    # tau — a narrower range (e.g. +/-8%) truncates real tail probability
    # mass and underestimates variance, confirmed by direct sweep.
    strikes = [forward + i * 50 for i in range(-80, 81)]

    chain = _bs_chain(forward, forward, strikes, sigma, tau)
    variance = model_free_variance(chain, forward, tau)

    assert variance == pytest.approx(sigma ** 2, rel=0.01)


def test_model_free_iv_recovers_flat_bs_vol():
    sigma = 0.18
    tau = 14 / 365
    forward = 51000.0
    strikes = [forward + i * 100 for i in range(-80, 81)]

    chain = _bs_chain(forward, forward, strikes, sigma, tau)
    iv = model_free_iv(chain, forward, tau)

    assert iv == pytest.approx(sigma, rel=0.01)


def test_model_free_variance_none_with_too_few_strikes():
    chain = [
        {"strike_price": 25000, "call_options": {"market_data": {"ltp": 100}},
         "put_options": {"market_data": {"ltp": 90}}},
    ]
    assert model_free_variance(chain, forward=25000, tau=30 / 365) is None


def test_model_free_variance_none_when_tau_not_positive():
    chain = _bs_chain(25000, 25000, [25000 + i * 50 for i in range(-5, 6)], 0.2, 30 / 365)
    assert model_free_variance(chain, forward=25000, tau=0) is None


def test_model_free_variance_wider_wings_are_closer_to_true_vol():
    """Sanity check on the discretization itself: truncating the strike
    range understates variance (missing tail contribution), so a narrower
    chain should read a lower model-free vol than a wider one built from
    the same underlying flat-vol surface.
    """
    sigma = 0.20
    tau = 30 / 365
    forward = 25000.0

    narrow_strikes = [forward + i * 50 for i in range(-5, 6)]
    wide_strikes = [forward + i * 50 for i in range(-80, 81)]

    narrow_chain = _bs_chain(forward, forward, narrow_strikes, sigma, tau)
    wide_chain = _bs_chain(forward, forward, wide_strikes, sigma, tau)

    narrow_iv = model_free_iv(narrow_chain, forward, tau)
    wide_iv = model_free_iv(wide_chain, forward, tau)

    assert narrow_iv < wide_iv
    assert wide_iv == pytest.approx(sigma, rel=0.01)
