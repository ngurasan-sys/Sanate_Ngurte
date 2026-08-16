from datetime import date

import pandas as pd
import pytest

from backend.app.backtest.strategies_catalog import STRATEGY_CATALOG, prepare_strategy


def _oi_row(timestamp, strike, option_type, close):
    return {"timestamp": pd.Timestamp(timestamp), "strike": strike, "option_type": option_type, "close": close}


def _oi_day(day_str, strike, ce_close, pe_close, n_bars=10):
    rows = []
    for i in range(n_bars):
        ts = f"{day_str} 09:{15 + i}"
        rows.append(_oi_row(ts, strike, "CE", ce_close + i))
        rows.append(_oi_row(ts, strike, "PE", pe_close + i))
    return rows


# Three-day panel: Oct 1 -> Oct 2 is an up move (24500 -> 24700), so Oct 3
# is labeled "UP" for the momentum strategies. Same ATM strike (24500)
# quoted every day to keep the fixture simple.
OI_DF = pd.DataFrame(
    _oi_day("2024-10-01", 24500, 100.0, 90.0)
    + _oi_day("2024-10-02", 24500, 110.0, 95.0)
    + _oi_day("2024-10-03", 24500, 120.0, 100.0)
)
SPOT_DF = pd.DataFrame([
    {"date": date(2024, 10, 1), "close": 24500.0},
    {"date": date(2024, 10, 2), "close": 24700.0},
    {"date": date(2024, 10, 3), "close": 24500.0},
])


def test_catalog_has_four_strategies_with_a_buying_majority():
    assert set(STRATEGY_CATALOG) == {"SHORT_STRADDLE", "LONG_STRADDLE", "LONG_CE_MOMENTUM", "LONG_PE_MOMENTUM"}
    long_count = sum(1 for m in STRATEGY_CATALOG.values() if m.direction == "longonly")
    assert long_count == 3  # buying-focused: only SHORT_STRADDLE sells


def test_prepare_strategy_rejects_unknown_name():
    with pytest.raises(ValueError, match="Unknown strategy"):
        prepare_strategy("NOT_A_STRATEGY", OI_DF, SPOT_DF, 1, 1)


def test_short_straddle_trades_every_day_and_is_shortonly():
    price_df, entries, exits, meta = prepare_strategy("SHORT_STRADDLE", OI_DF, SPOT_DF, 1, 1)
    assert meta.direction == "shortonly"
    assert meta.price_column == "straddle_premium"
    assert entries.sum() == 3  # all three days trade, no momentum gating


def test_long_straddle_same_series_as_short_but_longonly():
    price_df, entries, exits, meta = prepare_strategy("LONG_STRADDLE", OI_DF, SPOT_DF, 1, 1)
    assert meta.direction == "longonly"
    assert meta.price_column == "straddle_premium"
    assert entries.sum() == 3


def test_long_ce_momentum_only_trades_on_days_labeled_up():
    price_df, entries, exits, meta = prepare_strategy("LONG_CE_MOMENTUM", OI_DF, SPOT_DF, 1, 1)
    assert meta.direction == "longonly"
    assert meta.price_column == "premium"

    # Only Oct 3 is labeled "UP" (Oct1->Oct2 was the up move); Oct 1/2 have
    # no prior-pair label at all and must not trade.
    traded_days = set(price_df.loc[entries[entries].index, "day"])
    assert traded_days == {date(2024, 10, 3)}


def test_long_pe_momentum_finds_no_down_days_in_this_fixture():
    # The fixture only produces an "UP" label for Oct 3 — LONG_PE_MOMENTUM
    # should therefore place zero entries, not error out.
    price_df, entries, exits, meta = prepare_strategy("LONG_PE_MOMENTUM", OI_DF, SPOT_DF, 1, 1)
    assert entries.sum() == 0
    assert not price_df.empty  # the leg series itself still builds fine
