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
