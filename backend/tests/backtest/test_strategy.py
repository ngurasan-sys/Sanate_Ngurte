from datetime import date

import pandas as pd

from backend.app.backtest.strategy import build_daily_entry_exit_signals, compute_daily_entry_direction


def _straddle_df(day, n_bars, start_minute=15):
    timestamps = pd.date_range(f"2024-10-01 09:{start_minute}", periods=n_bars, freq="min")
    return pd.DataFrame({"timestamp": timestamps, "day": [day] * n_bars, "straddle_premium": [100.0] * n_bars})


def test_entry_and_exit_offsets_within_a_single_day():
    df = _straddle_df(date(2024, 10, 1), n_bars=50)
    entries, exits = build_daily_entry_exit_signals(df, entry_minutes_after_open=5, exit_minutes_before_close=5)

    assert entries.sum() == 1
    assert exits.sum() == 1
    entry_pos = entries[entries].index[0]
    exit_pos = exits[exits].index[0]
    assert entry_pos == 5
    assert exit_pos == 44  # last bar (49) minus 5
    assert exit_pos > entry_pos


def test_multiple_days_each_get_their_own_entry_exit():
    day1 = _straddle_df(date(2024, 10, 1), n_bars=30)
    day2 = _straddle_df(date(2024, 10, 2), n_bars=30)
    day2["timestamp"] = day2["timestamp"] + pd.Timedelta(days=1)
    df = pd.concat([day1, day2], ignore_index=True)

    entries, exits = build_daily_entry_exit_signals(df, entry_minutes_after_open=3, exit_minutes_before_close=3)

    assert entries.sum() == 2
    assert exits.sum() == 2


def test_day_too_short_for_entry_offset_is_skipped():
    df = _straddle_df(date(2024, 10, 1), n_bars=3)  # shorter than entry_minutes_after_open
    entries, exits = build_daily_entry_exit_signals(df, entry_minutes_after_open=5, exit_minutes_before_close=5)

    assert entries.sum() == 0
    assert exits.sum() == 0


def test_entry_never_lands_after_exit():
    # A day just long enough to have an entry but with exit offset pushing
    # past it — exit_index_in_day should clamp forward of entry, not collide.
    df = _straddle_df(date(2024, 10, 1), n_bars=8)
    entries, exits = build_daily_entry_exit_signals(df, entry_minutes_after_open=5, exit_minutes_before_close=5)

    if entries.sum() == 1:
        entry_pos = entries[entries].index[0]
        exit_pos = exits[exits].index[0]
        assert exit_pos > entry_pos


# --------------------------- active_days filtering ---------------------------

def test_active_days_restricts_entries_to_the_given_set():
    day1 = _straddle_df(date(2024, 10, 1), n_bars=30)
    day2 = _straddle_df(date(2024, 10, 2), n_bars=30)
    day2["timestamp"] = day2["timestamp"] + pd.Timedelta(days=1)
    df = pd.concat([day1, day2], ignore_index=True)

    entries, exits = build_daily_entry_exit_signals(
        df, entry_minutes_after_open=3, exit_minutes_before_close=3, active_days={date(2024, 10, 1)},
    )

    assert entries.sum() == 1
    assert exits.sum() == 1


def test_active_days_empty_set_yields_no_trades():
    df = _straddle_df(date(2024, 10, 1), n_bars=30)
    entries, exits = build_daily_entry_exit_signals(
        df, entry_minutes_after_open=3, exit_minutes_before_close=3, active_days=set(),
    )

    assert entries.sum() == 0
    assert exits.sum() == 0


def test_active_days_none_trades_every_day():
    day1 = _straddle_df(date(2024, 10, 1), n_bars=30)
    day2 = _straddle_df(date(2024, 10, 2), n_bars=30)
    day2["timestamp"] = day2["timestamp"] + pd.Timedelta(days=1)
    df = pd.concat([day1, day2], ignore_index=True)

    entries, exits = build_daily_entry_exit_signals(
        df, entry_minutes_after_open=3, exit_minutes_before_close=3, active_days=None,
    )

    assert entries.sum() == 2


# --------------------------- compute_daily_entry_direction ---------------------------

def _spot_df(rows):
    return pd.DataFrame([{"date": d, "close": c} for d, c in rows])


def test_direction_labels_day_from_the_prior_days_own_move():
    # Oct 1 -> Oct 2 is up (100 -> 110). That "UP" move should label the
    # entry direction for Oct 3, not Oct 2 itself.
    spot_df = _spot_df([
        (date(2024, 10, 1), 100.0),
        (date(2024, 10, 2), 110.0),
        (date(2024, 10, 3), 105.0),  # Oct 3's own close is irrelevant to its own label
    ])
    direction = compute_daily_entry_direction(spot_df)

    assert date(2024, 10, 2) not in direction  # no D-2 pair available yet
    assert direction[date(2024, 10, 3)] == "UP"


def test_direction_does_not_leak_the_labeled_days_own_close():
    """The defining look-ahead check: two spot histories that differ only
    in day 3's own close (which should never be consulted when labeling
    day 3) must produce the identical label for day 3.
    """
    base = [(date(2024, 10, 1), 100.0), (date(2024, 10, 2), 110.0)]
    spot_df_a = _spot_df(base + [(date(2024, 10, 3), 50.0)])   # day 3 crashes
    spot_df_b = _spot_df(base + [(date(2024, 10, 3), 500.0)])  # day 3 rallies

    assert compute_daily_entry_direction(spot_df_a)[date(2024, 10, 3)] == \
        compute_daily_entry_direction(spot_df_b)[date(2024, 10, 3)] == "UP"


def test_direction_down_and_flat():
    spot_df = _spot_df([
        (date(2024, 10, 1), 110.0),
        (date(2024, 10, 2), 100.0),  # down move -> labels Oct 3
        (date(2024, 10, 3), 100.0),
        (date(2024, 10, 4), 100.0),  # Oct 3 -> Oct 4 is flat -> labels Oct 4 as "FLAT"
    ])
    direction = compute_daily_entry_direction(spot_df)

    assert direction[date(2024, 10, 3)] == "DOWN"
    assert direction[date(2024, 10, 4)] == "FLAT"
