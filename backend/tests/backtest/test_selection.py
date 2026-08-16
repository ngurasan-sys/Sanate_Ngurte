from datetime import date

import pandas as pd
import pytest

from backend.app.backtest.selection import build_daily_leg_series, build_daily_straddle_series, select_atm_strike


# --------------------------- select_atm_strike ---------------------------

def test_select_atm_strike_nearest():
    assert select_atm_strike(24530.0, [24400, 24450, 24500, 24550, 24600]) == 24550


def test_select_atm_strike_exact_match():
    assert select_atm_strike(24500.0, [24400, 24450, 24500, 24550]) == 24500


def test_select_atm_strike_empty_list_returns_none():
    assert select_atm_strike(24500.0, []) is None


# --------------------------- build_daily_straddle_series ---------------------------

def _oi_row(timestamp, strike, option_type, close):
    return {"timestamp": pd.Timestamp(timestamp), "strike": strike, "option_type": option_type, "close": close}


def test_build_daily_straddle_series_basic():
    oi_df = pd.DataFrame([
        _oi_row("2024-10-01 09:15", 24500, "CE", 100.0),
        _oi_row("2024-10-01 09:15", 24500, "PE", 90.0),
        _oi_row("2024-10-01 09:16", 24500, "CE", 101.0),
        _oi_row("2024-10-01 09:16", 24500, "PE", 89.0),
        # A different strike present the same day — should NOT be picked (24500 is closer to spot 24510).
        _oi_row("2024-10-01 09:15", 24600, "CE", 40.0),
        _oi_row("2024-10-01 09:15", 24600, "PE", 130.0),
    ])
    spot_df = pd.DataFrame([{"date": date(2024, 10, 1), "close": 24510.0}])

    result = build_daily_straddle_series(oi_df, spot_df)

    assert len(result) == 2
    assert (result["strike"] == 24500).all()
    assert result.iloc[0]["straddle_premium"] == pytest.approx(190.0)
    assert result.iloc[1]["straddle_premium"] == pytest.approx(190.0)


def test_build_daily_straddle_series_skips_day_missing_spot():
    oi_df = pd.DataFrame([_oi_row("2024-10-01 09:15", 24500, "CE", 100.0), _oi_row("2024-10-01 09:15", 24500, "PE", 90.0)])
    spot_df = pd.DataFrame([{"date": date(2024, 10, 2), "close": 24510.0}])  # different day

    result = build_daily_straddle_series(oi_df, spot_df)
    assert result.empty


def test_build_daily_straddle_series_skips_day_missing_one_leg():
    # ATM strike has only CE quoted that day, no PE at all.
    oi_df = pd.DataFrame([_oi_row("2024-10-01 09:15", 24500, "CE", 100.0)])
    spot_df = pd.DataFrame([{"date": date(2024, 10, 1), "close": 24500.0}])

    result = build_daily_straddle_series(oi_df, spot_df)
    assert result.empty


def test_build_daily_straddle_series_multiple_days():
    oi_df = pd.DataFrame([
        _oi_row("2024-10-01 09:15", 24500, "CE", 100.0),
        _oi_row("2024-10-01 09:15", 24500, "PE", 90.0),
        _oi_row("2024-10-02 09:15", 24700, "CE", 80.0),
        _oi_row("2024-10-02 09:15", 24700, "PE", 70.0),
    ])
    spot_df = pd.DataFrame([
        {"date": date(2024, 10, 1), "close": 24500.0},
        {"date": date(2024, 10, 2), "close": 24710.0},
    ])

    result = build_daily_straddle_series(oi_df, spot_df)
    assert len(result) == 2
    assert list(result["day"]) == [date(2024, 10, 1), date(2024, 10, 2)]
    assert list(result["strike"]) == [24500, 24700]


# --------------------------- build_daily_leg_series ---------------------------

def test_build_daily_leg_series_extracts_only_the_requested_leg():
    oi_df = pd.DataFrame([
        _oi_row("2024-10-01 09:15", 24500, "CE", 100.0),
        _oi_row("2024-10-01 09:15", 24500, "PE", 90.0),
        _oi_row("2024-10-01 09:16", 24500, "CE", 101.0),
        _oi_row("2024-10-01 09:16", 24500, "PE", 89.0),
    ])
    spot_df = pd.DataFrame([{"date": date(2024, 10, 1), "close": 24500.0}])

    ce_result = build_daily_leg_series(oi_df, spot_df, "CE")
    assert len(ce_result) == 2
    assert list(ce_result["premium"]) == [100.0, 101.0]
    assert (ce_result["strike"] == 24500).all()

    pe_result = build_daily_leg_series(oi_df, spot_df, "PE")
    assert list(pe_result["premium"]) == [90.0, 89.0]


def test_build_daily_leg_series_skips_day_missing_the_requested_leg():
    # ATM strike has only CE quoted that day — asking for PE should skip it.
    oi_df = pd.DataFrame([_oi_row("2024-10-01 09:15", 24500, "CE", 100.0)])
    spot_df = pd.DataFrame([{"date": date(2024, 10, 1), "close": 24500.0}])

    result = build_daily_leg_series(oi_df, spot_df, "PE")
    assert result.empty


def test_build_daily_leg_series_picks_atm_strike_same_as_straddle_builder():
    oi_df = pd.DataFrame([
        _oi_row("2024-10-01 09:15", 24500, "CE", 100.0),
        _oi_row("2024-10-01 09:15", 24600, "CE", 40.0),  # further from spot 24510 — should not be picked
    ])
    spot_df = pd.DataFrame([{"date": date(2024, 10, 1), "close": 24510.0}])

    result = build_daily_leg_series(oi_df, spot_df, "CE")
    assert len(result) == 1
    assert result.iloc[0]["strike"] == 24500
    assert result.iloc[0]["premium"] == 100.0
