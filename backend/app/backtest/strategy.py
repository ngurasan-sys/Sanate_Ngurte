"""Pure signal-construction shared across every strategy in
strategies_catalog.py: one daily entry/forced-exit signal builder, plus
the prior-day momentum labeling the two directional buying strategies
gate their entries on.

Deliberately does NOT hand-roll intraday stop-loss/target scanning —
vectorbt's own Portfolio.from_signals(sl_stop=..., tp_stop=...) already
does that correctly and fast (vectorized/numba-compiled), which is the
whole reason to use vectorbt instead of a bar-by-bar Python loop. This
module's job is just: one entry signal per day, one forced time-based
exit signal per day (the backstop if neither SL nor TP fires first) —
engine.py passes sl_stop/tp_stop straight through to vectorbt.
"""

from datetime import date
from typing import Dict, Optional, Set, Tuple

import pandas as pd


def build_daily_entry_exit_signals(
    price_df: pd.DataFrame,
    entry_minutes_after_open: int,
    exit_minutes_before_close: int,
    active_days: Optional[Set[date]] = None,
) -> Tuple[pd.Series, pd.Series]:
    """entries/exits are boolean Series aligned to price_df's row order
    (not its timestamp index — vectorbt works off positional/row
    alignment with the price series it's given, which is
    price_df[meta.price_column] in engine.py).

    Per day: entry fires at the `entry_minutes_after_open`-th bar (skips
    the noisy open), exit fires at the bar `exit_minutes_before_close`
    minutes before that day's last bar (forced square-off backstop —
    SL/TP may fire earlier, handled by vectorbt itself).

    `active_days`, if given, restricts entries to that set of days —
    every other day gets no entry/exit at all. Used by directional
    single-leg strategies (buy CE only on days a momentum signal calls
    for "UP", etc.); omitted (None) trades every day, as the straddle
    strategies do.
    """
    entries = pd.Series(False, index=price_df.index)
    exits = pd.Series(False, index=price_df.index)

    for day, day_positions in price_df.groupby("day").indices.items():
        if active_days is not None and day not in active_days:
            continue

        day_positions = sorted(day_positions)
        if len(day_positions) <= entry_minutes_after_open:
            continue  # too short a session to even reach the entry offset

        entry_pos = day_positions[entry_minutes_after_open]
        exit_index_in_day = max(len(day_positions) - 1 - exit_minutes_before_close, entry_minutes_after_open + 1)
        if exit_index_in_day >= len(day_positions):
            exit_index_in_day = len(day_positions) - 1
        exit_pos = day_positions[exit_index_in_day]

        if exit_pos <= entry_pos:
            continue  # not enough bars between entry and a sane forced exit

        entries.iloc[entry_pos] = True
        exits.iloc[exit_pos] = True

    return entries, exits


def compute_daily_entry_direction(spot_df: pd.DataFrame) -> Dict[date, str]:
    """For each tradable day D (from the third day in spot_df onward),
    labels the *entry* direction using only information available before
    D's session starts: the prior day's own move, i.e. D-1's close vs
    D-2's close — "UP", "DOWN", or "FLAT".

    Deliberately NOT "D's close vs D-1's close": that would compare a day
    to itself and bake that day's own outcome into the decision of
    whether to buy at that day's open — a look-ahead bug for any
    strategy that has to commit to a direction before the session's
    result is known. The first two days in spot_df have no such prior
    pair and are left unlabeled.
    """
    spot_df = spot_df.sort_values("date")
    closes = dict(zip(spot_df["date"], spot_df["close"]))
    days = sorted(closes)

    direction: Dict[date, str] = {}
    for i in range(2, len(days)):
        prev_close = closes[days[i - 1]]
        prev_prev_close = closes[days[i - 2]]
        if prev_close > prev_prev_close:
            direction[days[i]] = "UP"
        elif prev_close < prev_prev_close:
            direction[days[i]] = "DOWN"
        else:
            direction[days[i]] = "FLAT"
    return direction
