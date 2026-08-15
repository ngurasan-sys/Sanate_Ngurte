import numpy as np
import pytest

from backend.app.strategies.option_analytics.svi import (
    SviParams,
    extract_smile,
    fit_svi,
    is_arbitrage_free,
    svi_atm_iv,
    svi_iv,
    svi_skew_proxy,
    svi_total_variance,
    synthetic_forward,
)


def _row(strike, call_iv=None, put_iv=None, call_ltp=50.0, put_ltp=50.0):
    return {
        "strike_price": strike,
        "call_options": {
            "market_data": {"ltp": call_ltp},
            "option_greeks": {"iv": call_iv},
        },
        "put_options": {
            "market_data": {"ltp": put_ltp},
            "option_greeks": {"iv": put_iv},
        },
    }


# --------------------------- forward price ---------------------------

def test_synthetic_forward_from_put_call_parity():
    # ATM strike 24500: call - put = 5 => F = 24500 + 5
    chain = [_row(24500, call_ltp=105.0, put_ltp=100.0)]
    assert synthetic_forward(chain, spot=24480) == 24505.0


def test_synthetic_forward_falls_back_to_spot_when_missing_ltp():
    chain = [_row(24500, call_ltp=None, put_ltp=None)]
    assert synthetic_forward(chain, spot=24480) == 24480


# --------------------------- smile extraction ---------------------------

def test_extract_smile_skips_strikes_with_no_valid_iv():
    chain = [
        _row(24000, call_iv=0.0, put_iv=0.0),   # both invalid -> skipped
        _row(24500, call_iv=12.0, put_iv=12.0), # ATM
        _row(25000, call_iv=None, put_iv=11.0), # one-sided, still usable
    ]
    x, w = extract_smile(chain, forward=24500, tau=30 / 365)
    assert len(x) == 2
    assert x[0] == pytest.approx(0.0)  # ln(24500/24500)
    assert w[0] == pytest.approx((0.12 ** 2) * (30 / 365))


# --------------------------- SVI curve fit ---------------------------

def test_fit_svi_recovers_known_parameters():
    """Generate a smile from known SVI params, fit it back, and check the
    fitted curve reproduces the same total variance — the real check,
    since the raw parameters themselves are not identifiable uniquely.
    """
    true_params = SviParams(a=0.02, b=0.15, rho=-0.4, m=0.0, sigma=0.2)
    x = np.linspace(-0.3, 0.3, 15)
    w = svi_total_variance(true_params, x)

    fitted = fit_svi(x, w)

    assert svi_total_variance(fitted, x) == pytest.approx(w, abs=1e-4)
    assert is_arbitrage_free(fitted)


def test_fit_svi_raises_with_too_few_points():
    with pytest.raises(ValueError):
        fit_svi(np.array([0.0, 0.1]), np.array([0.02, 0.021]))


def test_svi_atm_iv_matches_direct_calculation():
    params = SviParams(a=0.02, b=0.15, rho=-0.4, m=0.0, sigma=0.2)
    tau = 30 / 365
    w0 = svi_total_variance(params, np.array([0.0]))[0]
    assert svi_atm_iv(params, tau) == pytest.approx(np.sqrt(w0 / tau))


def test_svi_skew_proxy_positive_for_negative_rho():
    # Negative rho (downside skew, typical for index puts) should make
    # OTM put IV richer than OTM call IV at the same log-moneyness offset.
    params = SviParams(a=0.02, b=0.15, rho=-0.4, m=0.0, sigma=0.2)
    assert svi_skew_proxy(params, tau=30 / 365) > 0


def test_is_arbitrage_free_rejects_invalid_params():
    assert is_arbitrage_free(SviParams(a=0.02, b=-0.1, rho=0.0, m=0.0, sigma=0.2)) == False
    assert is_arbitrage_free(SviParams(a=0.02, b=0.1, rho=1.5, m=0.0, sigma=0.2)) == False
    assert is_arbitrage_free(SviParams(a=-1.0, b=0.01, rho=0.0, m=0.0, sigma=0.01)) == False
