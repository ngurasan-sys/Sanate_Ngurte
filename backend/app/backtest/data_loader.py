"""Loads the converted Parquet OI-buildup dataset and the raw daily spot
CSVs. Kept separate from selection.py/strategy.py (which are pure and
unit-testable against tiny synthetic frames) since this module touches
the filesystem.
"""

from datetime import date
from pathlib import Path
from typing import List

import pandas as pd

from .config import OI_PARQUET_DIR, RAW_EXPORTS_DIR

SUPPORTED_UNDERLYINGS = ("NIFTY", "SENSEX")


class BacktestDataError(Exception):
    """Raised when the requested backtest data isn't available on disk —
    e.g. the ETL script hasn't been run yet, or the date range falls
    outside what was exported.
    """


def _year_months_in_range(date_from: date, date_to: date) -> List[str]:
    months = []
    cursor = date_from.replace(day=1)
    while cursor <= date_to:
        months.append(cursor.strftime("%Y-%m"))
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return months


def load_oi_data(underlying: str, date_from: date, date_to: date) -> pd.DataFrame:
    """Reads only the Parquet month-partitions overlapping [date_from,
    date_to] — not the whole dataset — then filters to the exact range.
    """
    if underlying not in SUPPORTED_UNDERLYINGS:
        raise BacktestDataError(f"Unsupported underlying {underlying!r}. Supported: {list(SUPPORTED_UNDERLYINGS)}.")

    underlying_dir = OI_PARQUET_DIR / underlying
    if not underlying_dir.exists():
        raise BacktestDataError(
            f"No converted OI data found at {underlying_dir}. Run "
            f"backend/scripts/convert_oi_data_to_parquet.py first."
        )

    frames = []
    for year_month in _year_months_in_range(date_from, date_to):
        partition = underlying_dir / f"year_month={year_month}" / "data.parquet"
        if partition.exists():
            frames.append(pd.read_parquet(partition))

    if not frames:
        raise BacktestDataError(
            f"No OI data found for {underlying} between {date_from} and {date_to} "
            f"under {underlying_dir}."
        )

    df = pd.concat(frames, ignore_index=True)
    df = df[(df["timestamp"].dt.date >= date_from) & (df["timestamp"].dt.date <= date_to)]
    if df.empty:
        raise BacktestDataError(f"No OI rows fall within {date_from}..{date_to} for {underlying}.")
    return df.sort_values("timestamp").reset_index(drop=True)


def load_daily_spot(underlying: str, date_from: date, date_to: date) -> pd.DataFrame:
    """Reads the small *_day.csv export directly — no ETL needed. Used
    only to pick each day's ATM strike (see selection.py), not as the
    tradable series itself.
    """
    if underlying not in SUPPORTED_UNDERLYINGS:
        raise BacktestDataError(f"Unsupported underlying {underlying!r}. Supported: {list(SUPPORTED_UNDERLYINGS)}.")

    csv_path = RAW_EXPORTS_DIR / f"{underlying}_day.csv"
    if not csv_path.exists():
        raise BacktestDataError(f"No daily spot file found at {csv_path}.")

    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df = df[(df["date"] >= date_from) & (df["date"] <= date_to)]
    if df.empty:
        raise BacktestDataError(f"No daily spot rows fall within {date_from}..{date_to} for {underlying}.")
    return df.sort_values("date").reset_index(drop=True)
