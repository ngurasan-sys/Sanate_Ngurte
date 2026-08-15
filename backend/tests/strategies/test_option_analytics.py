import pytest

from backend.app.strategies.option_analytics.analysis import (
    classify_iv_regime,
    classify_pcr_zone,
    classify_skew_bias,
    compute_iv_skew,
    compute_total_pcr,
    detect_pcr_reversal,
    extract_atm_iv,
    is_valid_iv,
    iv_signal_for_regime,
)
from backend.app.strategies.option_analytics.engine import OptionAnalyticsEngine
from backend.app.strategies.option_analytics.models import OptionAnalyticsConfig


def _row(strike, spot=24500, call_iv=12.0, put_iv=12.0, call_oi=100000, put_oi=100000):
    return {
        "strike_price": strike,
        "underlying_spot_price": spot,
        "call_options": {
            "market_data": {"oi": call_oi, "prev_oi": call_oi, "ltp": 50.0, "close_price": 50.0},
            "option_greeks": {"iv": call_iv},
        },
        "put_options": {
            "market_data": {"oi": put_oi, "prev_oi": put_oi, "ltp": 50.0, "close_price": 50.0},
            "option_greeks": {"iv": put_iv},
        },
    }


# --------------------------- IV validity ---------------------------

def test_is_valid_iv_rejects_zero_and_none():
    # Upstox returns 0.0 for illiquid strikes — a missing reading, not real.
    assert is_valid_iv(0.0) is False
    assert is_valid_iv(None) is False
    assert is_valid_iv(12.5) is True


def test_extract_atm_iv_averages_both_sides():
    chain = [_row(24500, call_iv=10.0, put_iv=14.0)]
    assert extract_atm_iv(chain, 24500) == 12.0


def test_extract_atm_iv_ignores_zero_side():
    chain = [_row(24500, call_iv=0.0, put_iv=14.0)]
    assert extract_atm_iv(chain, 24500) == 14.0


def test_extract_atm_iv_none_when_both_invalid():
    chain = [_row(24500, call_iv=0.0, put_iv=0.0)]
    assert extract_atm_iv(chain, 24500) is None


def test_extract_atm_iv_none_when_strike_absent():
    chain = [_row(24500)]
    assert extract_atm_iv(chain, 99999) is None


# --------------------------- IV regime ---------------------------

def test_classify_iv_regime_crush():
    regime, change = classify_iv_regime(11.0, 13.0, crush_drop_pct=8.0, expansion_rise_pct=8.0)
    assert regime == "IV_CRUSH"
    assert change < 0


def test_classify_iv_regime_expansion():
    regime, change = classify_iv_regime(15.0, 13.0, crush_drop_pct=8.0, expansion_rise_pct=8.0)
    assert regime == "IV_EXPANSION"
    assert change > 0


def test_classify_iv_regime_stable():
    regime, _ = classify_iv_regime(13.2, 13.0, crush_drop_pct=8.0, expansion_rise_pct=8.0)
    assert regime == "IV_STABLE"


def test_classify_iv_regime_unknown_without_baseline():
    regime, change = classify_iv_regime(13.0, None, 8.0, 8.0)
    assert regime == "UNKNOWN"
    assert change is None


def test_iv_signal_mapping():
    assert iv_signal_for_regime("IV_CRUSH") == "SELL_PREMIUM"
    assert iv_signal_for_regime("IV_EXPANSION") == "BUY_PREMIUM"
    assert iv_signal_for_regime("IV_STABLE") == "NONE"
    assert iv_signal_for_regime("UNKNOWN") == "NONE"


# --------------------------- IV skew ---------------------------

def test_compute_iv_skew_put_richer():
    strikes = [24350, 24400, 24450, 24500, 24550, 24600, 24650]
    chain = [_row(s, put_iv=18.0, call_iv=12.0) for s in strikes]
    skew = compute_iv_skew(chain, 24500, strike_offset=3)
    assert skew == pytest.approx(6.0)


def test_compute_iv_skew_none_when_offset_out_of_range():
    chain = [_row(s) for s in [24450, 24500, 24550]]
    assert compute_iv_skew(chain, 24500, strike_offset=3) is None


def test_compute_iv_skew_none_when_leg_iv_invalid():
    strikes = [24350, 24400, 24450, 24500, 24550, 24600, 24650]
    chain = [_row(s) for s in strikes]
    chain[0]["put_options"]["option_greeks"]["iv"] = 0.0  # illiquid OTM put
    assert compute_iv_skew(chain, 24500, strike_offset=3) is None


def test_classify_skew_bias():
    assert classify_skew_bias(5.0, 3.0) == "PUT_SKEW"
    assert classify_skew_bias(-5.0, 3.0) == "CALL_SKEW"
    assert classify_skew_bias(1.0, 3.0) == "NEUTRAL"
    assert classify_skew_bias(None, 3.0) == "NEUTRAL"


# --------------------------- PCR ---------------------------

def test_compute_total_pcr():
    chain = [_row(24500, call_oi=100000, put_oi=150000)]
    assert compute_total_pcr(chain) == pytest.approx(1.5)


def test_compute_total_pcr_none_without_call_oi():
    chain = [_row(24500, call_oi=0, put_oi=150000)]
    assert compute_total_pcr(chain) is None


def test_classify_pcr_zone():
    assert classify_pcr_zone(1.8, 1.5, 0.6) == "HIGH_EXTREME"
    assert classify_pcr_zone(0.4, 1.5, 0.6) == "LOW_EXTREME"
    assert classify_pcr_zone(1.0, 1.5, 0.6) == "NEUTRAL"


def test_detect_pcr_reversal_bullish_after_peak():
    history = [1.2, 1.4, 1.7, 1.65]
    signal, peak, trough, reasoning = detect_pcr_reversal(
        pcr=1.50, pcr_history=history, high_extreme=1.5, low_extreme=0.6, reversal_delta=0.15,
    )
    assert signal == "CONTRARIAN_BULLISH"
    assert peak == 1.7
    assert "turned down" in reasoning


def test_detect_pcr_reversal_bearish_after_trough():
    history = [0.9, 0.7, 0.5, 0.55]
    signal, peak, trough, reasoning = detect_pcr_reversal(
        pcr=0.68, pcr_history=history, high_extreme=1.5, low_extreme=0.6, reversal_delta=0.15,
    )
    assert signal == "CONTRARIAN_BEARISH"
    assert trough == 0.5
    assert "turned up" in reasoning


def test_detect_pcr_reversal_none_while_still_at_extreme():
    # Sitting at an extreme is not itself a signal — it can persist for hours.
    history = [1.6, 1.7, 1.75]
    signal, _, _, _ = detect_pcr_reversal(
        pcr=1.74, pcr_history=history, high_extreme=1.5, low_extreme=0.6, reversal_delta=0.15,
    )
    assert signal == "NONE"


def test_detect_pcr_reversal_none_without_history():
    signal, peak, trough, reasoning = detect_pcr_reversal(1.5, [], 1.5, 0.6, 0.15)
    assert signal == "NONE"
    assert peak is None


# --------------------------- Engine.analyse ---------------------------

def _chain(atm=24500, call_iv=12.0, put_iv=12.0, call_oi=100000, put_oi=100000):
    strikes = [atm + (i - 5) * 50 for i in range(11)]
    return [
        _row(s, spot=atm + 10, call_iv=call_iv, put_iv=put_iv, call_oi=call_oi, put_oi=put_oi)
        for s in strikes
    ]


def test_analyse_reports_insufficient_until_baseline_built():
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    snapshot = engine.analyse(_chain())

    # First sample has nothing to compare against — must say so honestly.
    assert snapshot.iv_regime.sufficient_data is False
    assert "baseline" in snapshot.iv_regime.reason.lower()
    assert snapshot.pcr_reversal.sufficient_data is False
    assert snapshot.atm_strike == 24500


def test_analyse_detects_iv_crush_against_baseline():
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    for _ in range(3):
        engine.analyse(_chain(call_iv=20.0, put_iv=20.0))  # build a 20.0 baseline

    snapshot = engine.analyse(_chain(call_iv=15.0, put_iv=15.0))  # -25%
    assert snapshot.iv_regime.sufficient_data is True
    assert snapshot.iv_regime.regime == "IV_CRUSH"
    assert snapshot.iv_regime.signal == "SELL_PREMIUM"


def test_analyse_detects_iv_expansion_against_baseline():
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    for _ in range(3):
        engine.analyse(_chain(call_iv=10.0, put_iv=10.0))

    snapshot = engine.analyse(_chain(call_iv=14.0, put_iv=14.0))  # +40%
    assert snapshot.iv_regime.regime == "IV_EXPANSION"
    assert snapshot.iv_regime.signal == "BUY_PREMIUM"


def test_analyse_current_sample_not_compared_against_itself():
    """The baseline must exclude the sample being classified, else a steady
    drift would never register as a regime change."""
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    engine.analyse(_chain(call_iv=20.0, put_iv=20.0))
    snapshot = engine.analyse(_chain(call_iv=20.0, put_iv=20.0))
    assert snapshot.iv_regime.baseline_iv == 20.0


def test_analyse_pcr_reversal_end_to_end():
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    # Drive PCR to a high extreme (put OI >> call OI), then back off.
    engine.analyse(_chain(call_oi=100000, put_oi=180000))  # pcr 1.8
    snapshot = engine.analyse(_chain(call_oi=100000, put_oi=150000))  # pcr 1.5, -0.3

    assert snapshot.pcr_reversal.sufficient_data is True
    assert snapshot.pcr_reversal.signal == "CONTRARIAN_BULLISH"
    assert snapshot.pcr_reversal.pcr == pytest.approx(1.5)


def test_analyse_handles_all_invalid_iv_without_crashing():
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    snapshot = engine.analyse(_chain(call_iv=0.0, put_iv=0.0))
    assert snapshot.iv_regime.sufficient_data is False
    assert snapshot.iv_regime.atm_iv is None


# --------------------------- Engine.analyse: SVI ---------------------------

def test_analyse_reports_svi_insufficient_without_expiry_field():
    # _chain() rows carry no "expiry" key — the real Upstox chain always
    # does, but a malformed/partial chain shouldn't crash the snapshot,
    # just degrade this one field honestly.
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    snapshot = engine.analyse(_chain())
    assert snapshot.svi.sufficient_data is False
    assert "expiry" in snapshot.svi.reason.lower()


def _chain_with_expiry(atm=24500, expiry="2099-01-01", base_iv=12.0):
    """Smile with a real skew (put IV richer than call IV, rising away from
    ATM) so the SVI fit has actual curvature to recover, not a flat line.
    """
    strikes = [atm + (i - 5) * 50 for i in range(11)]
    rows = []
    for s in strikes:
        moneyness = (s - atm) / atm
        call_iv = base_iv + max(moneyness, 0) * 20
        put_iv = base_iv - min(moneyness, 0) * 30
        row = _row(s, spot=atm + 10, call_iv=call_iv, put_iv=put_iv)
        row["expiry"] = expiry
        rows.append(row)
    return rows


def test_analyse_fits_svi_when_expiry_present():
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    snapshot = engine.analyse(_chain_with_expiry())

    assert snapshot.svi.sufficient_data is True
    assert snapshot.svi.expiry == "2099-01-01"
    assert snapshot.svi.tau_years > 0
    assert snapshot.svi.atm_iv > 0
    assert snapshot.svi.arbitrage_free in (True, False)
    assert set(snapshot.svi.params.keys()) == {"a", "b", "rho", "m", "sigma"}


# --------------------------- Engine.analyse: VRP ---------------------------

def _simulated_closes(n=200, seed=5, start=24500.0):
    import numpy as np
    rng = np.random.default_rng(seed)
    sigma_daily = 0.15 / (252 ** 0.5)
    closes = [start]
    for r in rng.normal(0.0, sigma_daily, size=n):
        closes.append(closes[-1] * np.exp(r))
    return closes


def test_analyse_reports_vrp_insufficient_without_svi():
    # _chain() has no "expiry" -> SVI fails -> VRP must degrade too,
    # since it depends on SVI's implied vol.
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    snapshot = engine.analyse(_chain(), daily_closes=_simulated_closes())
    assert snapshot.vrp.sufficient_data is False
    assert "svi" in snapshot.vrp.reason.lower()


def test_analyse_reports_vrp_insufficient_without_daily_closes():
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    snapshot = engine.analyse(_chain_with_expiry(), daily_closes=None)
    assert snapshot.vrp.sufficient_data is False
    assert "closes" in snapshot.vrp.reason.lower()


def test_analyse_reports_vrp_insufficient_with_too_few_closes():
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    snapshot = engine.analyse(_chain_with_expiry(), daily_closes=[24500.0] * 10)
    assert snapshot.vrp.sufficient_data is False
    assert "har-rv" in snapshot.vrp.reason.lower()


def test_analyse_computes_vrp_when_svi_and_closes_available():
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    snapshot = engine.analyse(_chain_with_expiry(), daily_closes=_simulated_closes())

    assert snapshot.vrp.sufficient_data is True
    assert snapshot.vrp.implied_vol == snapshot.svi.atm_iv
    assert snapshot.vrp.forecast_vol > 0
    assert snapshot.vrp.vrp == pytest.approx(snapshot.vrp.implied_vol - snapshot.vrp.forecast_vol)
    # First reading ever -> no history yet to Z-score against.
    assert snapshot.vrp.z_score is None
    assert snapshot.vrp.classification == "UNKNOWN"
    assert snapshot.vrp.signal == "NONE"


def test_analyse_vrp_zscore_stays_none_while_history_has_zero_variance():
    # Identical chain/closes every poll -> identical VRP every time -> zero
    # variance in the rolling history -> vrp_zscore legitimately returns
    # None (see test_vrp.py::test_vrp_zscore_none_with_zero_variance_history),
    # not a divide-by-zero crash.
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    closes = _simulated_closes()

    for _ in range(5):
        engine.analyse(_chain_with_expiry(), daily_closes=closes)

    snapshot = engine.analyse(_chain_with_expiry(), daily_closes=closes)
    assert snapshot.vrp.sufficient_data is True
    assert snapshot.vrp.z_score is None
    assert snapshot.vrp.classification == "UNKNOWN"


def test_analyse_vrp_zscore_becomes_available_once_history_has_variance():
    # vrp_zscore standardizes against the *history* recorded so far (see
    # _compute_vrp_state: it reads self._vrp_history before this poll's
    # reading is appended) — so the history itself needs varying readings,
    # not just a current reading that differs from a still-uniform one.
    engine = OptionAnalyticsEngine(OptionAnalyticsConfig())
    closes = _simulated_closes()

    for base_iv in [10.0, 12.0, 14.0, 16.0, 18.0]:
        engine.analyse(_chain_with_expiry(base_iv=base_iv), daily_closes=closes)

    snapshot = engine.analyse(_chain_with_expiry(base_iv=20.0), daily_closes=closes)
    assert snapshot.vrp.sufficient_data is True
    assert snapshot.vrp.z_score is not None
    assert snapshot.vrp.classification in ("IV_RICH", "IV_CHEAP", "NEUTRAL")
