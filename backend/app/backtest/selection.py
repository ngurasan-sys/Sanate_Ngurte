"""Pure, stateless logic for turning the raw per-strike OI-buildup panel
into a single tradable "short ATM straddle" price series — unit-testable
against tiny synthetic frames, no filesystem/network involved. Mirrors
the analysis.py/engine.py split used throughout this codebase
(option_analytics, manual_trading, cas_dislocation).

The OI-buildup export has no spot column — only strike/option_type/OHLCV
per minute. ATM selection therefore has to come from the daily spot
close (*_day.csv), picked once per trading day and held fixed for that
day — a daily-ATM approximation, not an intraday-recomputed one. Good
enough for a first backtest; a synthetic-forward-from-chain approach
(as used live in option_analytics/svi.py) would need the full chain
pivoted wide at every minute, which this long-format export doesn't
cheaply support.
"""

from typing import List, Optional

import pandas as pd


def select_atm_strike(spot_close: float, available_strikes: List[float]) -> Optional[float]:
    """Nearest available strike to the day's spot close. None with no
    strikes to choose from — the caller must skip that day, not guess.
    """
    if not available_strikes:
        return None
    return min(available_strikes, key=lambda k: abs(k - spot_close))


def build_daily_straddle_series(oi_df: pd.DataFrame, spot_df: pd.DataFrame) -> pd.DataFrame:
    """For each trading day present in oi_df: pick that day's ATM strike
    from spot_df's close, then extract the CE+PE minute bars for exactly
    that strike and combine them into a single "short straddle" premium
    series (ce_close + pe_close).

    Days missing a spot close, or where the chosen ATM strike doesn't
    have both CE and PE quoted that day, are skipped — silently dropping
    a day is safer here than fabricating a partial straddle leg.

    Returns a DataFrame with columns:
    timestamp, day, strike, ce_close, pe_close, straddle_premium
    sorted chronologically. Empty (not an error) if nothing matched.
    """
    oi_df = oi_df.copy()
    oi_df["day"] = oi_df["timestamp"].dt.date
    spot_by_day = dict(zip(spot_df["date"], spot_df["close"]))

    daily_frames = []
    for day, day_group in oi_df.groupby("day"):
        spot_close = spot_by_day.get(day)
        if spot_close is None:
            continue

        available_strikes = sorted(day_group["strike"].unique())
        atm_strike = select_atm_strike(spot_close, available_strikes)
        if atm_strike is None:
            continue

        strike_group = day_group[day_group["strike"] == atm_strike]
        ce = strike_group[strike_group["option_type"] == "CE"][["timestamp", "close"]].rename(columns={"close": "ce_close"})
        pe = strike_group[strike_group["option_type"] == "PE"][["timestamp", "close"]].rename(columns={"close": "pe_close"})
        if ce.empty or pe.empty:
            continue

        merged = pd.merge(ce, pe, on="timestamp", how="inner").sort_values("timestamp")
        if merged.empty:
            continue

        merged["day"] = day
        merged["strike"] = atm_strike
        merged["straddle_premium"] = merged["ce_close"] + merged["pe_close"]
        daily_frames.append(merged)

    if not daily_frames:
        return pd.DataFrame(columns=["timestamp", "day", "strike", "ce_close", "pe_close", "straddle_premium"])

    result = pd.concat(daily_frames, ignore_index=True)
    return result.sort_values("timestamp").reset_index(drop=True)


def build_daily_leg_series(oi_df: pd.DataFrame, spot_df: pd.DataFrame, option_type: str) -> pd.DataFrame:
    """Same daily-ATM-strike selection as build_daily_straddle_series, but
    extracts a single option leg (CE or PE) instead of combining both —
    the price series a single-leg directional strategy (e.g. buying CE
    or PE outright) trades against.

    Returns columns: timestamp, day, strike, premium. Empty (not an
    error) if nothing matched.
    """
    oi_df = oi_df.copy()
    oi_df["day"] = oi_df["timestamp"].dt.date
    spot_by_day = dict(zip(spot_df["date"], spot_df["close"]))

    daily_frames = []
    for day, day_group in oi_df.groupby("day"):
        spot_close = spot_by_day.get(day)
        if spot_close is None:
            continue

        available_strikes = sorted(day_group["strike"].unique())
        atm_strike = select_atm_strike(spot_close, available_strikes)
        if atm_strike is None:
            continue

        leg = day_group[(day_group["strike"] == atm_strike) & (day_group["option_type"] == option_type)]
        leg = leg[["timestamp", "close"]].rename(columns={"close": "premium"}).sort_values("timestamp")
        if leg.empty:
            continue

        leg["day"] = day
        leg["strike"] = atm_strike
        daily_frames.append(leg)

    if not daily_frames:
        return pd.DataFrame(columns=["timestamp", "day", "strike", "premium"])

    result = pd.concat(daily_frames, ignore_index=True)
    return result.sort_values("timestamp").reset_index(drop=True)
