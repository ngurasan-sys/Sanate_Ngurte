"""Catalog of backtestable strategies and the dispatcher that turns a
BacktestRequest's `strategy` selection into a tradable price series plus
entry/exit signals — the layer the frontend's strategy selector maps to.

Every strategy resolves to one of two price series:
- a combined CE+PE "straddle" premium (short = sell volatility, long =
  buy volatility), or
- a single CE or PE leg, entered only on days a prior-day momentum
  signal calls for that direction — the "buying" strategy family this
  catalog leans on, since SHORT_STRADDLE was the only strategy v1 shipped
  with and is a *selling* strategy.

vectorbt handles the actual SL/TP scanning once a (price, entries, exits,
direction) tuple is produced here — this module's only job is picking
which series and which days feed vectorbt, not simulating the trade.
"""

from dataclasses import dataclass
from typing import Dict, Tuple

import pandas as pd

from .selection import build_daily_leg_series, build_daily_straddle_series
from .strategy import build_daily_entry_exit_signals, compute_daily_entry_direction


@dataclass(frozen=True)
class StrategyMeta:
    name: str
    label: str
    description: str
    direction: str      # "shortonly" | "longonly" — passed straight to vectorbt
    price_column: str   # which column in the prepared price_df holds the tradable premium


STRATEGY_CATALOG: Dict[str, StrategyMeta] = {
    "SHORT_STRADDLE": StrategyMeta(
        name="SHORT_STRADDLE",
        label="Short ATM Straddle",
        description="Sell the ATM call+put daily, buy back on SL/target/time-exit. Profits from low realized volatility.",
        direction="shortonly",
        price_column="straddle_premium",
    ),
    "LONG_STRADDLE": StrategyMeta(
        name="LONG_STRADDLE",
        label="Long ATM Straddle",
        description="Buy the ATM call+put daily. Profits from a big move in either direction exceeding the combined premium paid.",
        direction="longonly",
        price_column="straddle_premium",
    ),
    "LONG_CE_MOMENTUM": StrategyMeta(
        name="LONG_CE_MOMENTUM",
        label="Long CE (Momentum)",
        description="Buy the ATM call, but only on days following an up day (yesterday's close above the day before it). Directional option buying.",
        direction="longonly",
        price_column="premium",
    ),
    "LONG_PE_MOMENTUM": StrategyMeta(
        name="LONG_PE_MOMENTUM",
        label="Long PE (Momentum)",
        description="Buy the ATM put, but only on days following a down day (yesterday's close below the day before it). Directional option buying.",
        direction="longonly",
        price_column="premium",
    ),
}


def prepare_strategy(
    strategy_name: str,
    oi_df: pd.DataFrame,
    spot_df: pd.DataFrame,
    entry_minutes_after_open: int,
    exit_minutes_before_close: int,
) -> Tuple[pd.DataFrame, pd.Series, pd.Series, StrategyMeta]:
    """Returns (price_df, entries, exits, meta). price_df carries "day"
    and "strike" columns either way, plus meta.price_column holding the
    tradable premium — engine.py reads that column name rather than
    guessing which one is present.
    """
    if strategy_name not in STRATEGY_CATALOG:
        raise ValueError(f"Unknown strategy {strategy_name!r}. Available: {list(STRATEGY_CATALOG)}.")

    meta = STRATEGY_CATALOG[strategy_name]

    if strategy_name in ("SHORT_STRADDLE", "LONG_STRADDLE"):
        price_df = build_daily_straddle_series(oi_df, spot_df)
        entries, exits = build_daily_entry_exit_signals(price_df, entry_minutes_after_open, exit_minutes_before_close)
        return price_df, entries, exits, meta

    option_type = "CE" if strategy_name == "LONG_CE_MOMENTUM" else "PE"
    wanted_direction = "UP" if strategy_name == "LONG_CE_MOMENTUM" else "DOWN"

    price_df = build_daily_leg_series(oi_df, spot_df, option_type)
    entry_direction_by_day = compute_daily_entry_direction(spot_df)
    active_days = {day for day, direction in entry_direction_by_day.items() if direction == wanted_direction}

    entries, exits = build_daily_entry_exit_signals(
        price_df, entry_minutes_after_open, exit_minutes_before_close, active_days=active_days,
    )
    return price_df, entries, exits, meta
