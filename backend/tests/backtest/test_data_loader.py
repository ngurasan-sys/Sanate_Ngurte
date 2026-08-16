from datetime import date

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from backend.app.backtest import data_loader as data_loader_module
from backend.app.backtest.data_loader import (
    BacktestDataError,
    load_daily_spot,
    load_oi_data,
)


@pytest.fixture
def synthetic_dirs(tmp_path, monkeypatch):
    oi_dir = tmp_path / "oi_parquet"
    exports_dir = tmp_path / "exports"
    monkeypatch.setattr(data_loader_module, "OI_PARQUET_DIR", oi_dir)
    monkeypatch.setattr(data_loader_module, "RAW_EXPORTS_DIR", exports_dir)
    return oi_dir, exports_dir


def _write_partition(oi_dir, underlying, year_month, rows):
    partition_dir = oi_dir / underlying / f"year_month={year_month}"
    partition_dir.mkdir(parents=True)
    df = pd.DataFrame(rows)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), partition_dir / "data.parquet")


def test_load_oi_data_unsupported_underlying_raises(synthetic_dirs):
    with pytest.raises(BacktestDataError, match="Unsupported underlying"):
        load_oi_data("FINNIFTY", date(2024, 10, 1), date(2024, 10, 2))


def test_load_oi_data_missing_directory_raises(synthetic_dirs):
    with pytest.raises(BacktestDataError, match="Run backend/scripts"):
        load_oi_data("NIFTY", date(2024, 10, 1), date(2024, 10, 2))


def test_load_oi_data_reads_only_overlapping_months(synthetic_dirs):
    oi_dir, _ = synthetic_dirs
    _write_partition(oi_dir, "NIFTY", "2024-10", [
        {"timestamp": pd.Timestamp("2024-10-01 09:15"), "strike": 24500.0, "option_type": "CE", "close": 100.0},
    ])
    _write_partition(oi_dir, "NIFTY", "2024-11", [
        {"timestamp": pd.Timestamp("2024-11-01 09:15"), "strike": 24500.0, "option_type": "CE", "close": 105.0},
    ])

    result = load_oi_data("NIFTY", date(2024, 10, 1), date(2024, 10, 31))
    assert len(result) == 1
    assert result.iloc[0]["close"] == 100.0


def test_load_oi_data_filters_exact_date_range_within_a_partition(synthetic_dirs):
    oi_dir, _ = synthetic_dirs
    _write_partition(oi_dir, "NIFTY", "2024-10", [
        {"timestamp": pd.Timestamp("2024-10-01 09:15"), "strike": 24500.0, "option_type": "CE", "close": 100.0},
        {"timestamp": pd.Timestamp("2024-10-15 09:15"), "strike": 24500.0, "option_type": "CE", "close": 110.0},
        {"timestamp": pd.Timestamp("2024-10-31 09:15"), "strike": 24500.0, "option_type": "CE", "close": 120.0},
    ])

    result = load_oi_data("NIFTY", date(2024, 10, 10), date(2024, 10, 20))
    assert len(result) == 1
    assert result.iloc[0]["close"] == 110.0


def test_load_oi_data_empty_range_raises(synthetic_dirs):
    oi_dir, _ = synthetic_dirs
    _write_partition(oi_dir, "NIFTY", "2024-10", [
        {"timestamp": pd.Timestamp("2024-10-01 09:15"), "strike": 24500.0, "option_type": "CE", "close": 100.0},
    ])

    with pytest.raises(BacktestDataError, match="No OI rows fall within"):
        load_oi_data("NIFTY", date(2024, 10, 20), date(2024, 10, 25))


def test_load_daily_spot_missing_file_raises(synthetic_dirs):
    with pytest.raises(BacktestDataError, match="No daily spot file"):
        load_daily_spot("NIFTY", date(2024, 10, 1), date(2024, 10, 2))


def test_load_daily_spot_filters_range(synthetic_dirs):
    _, exports_dir = synthetic_dirs
    exports_dir.mkdir(parents=True)
    pd.DataFrame([
        {"timestamp": "2024-10-01 00:00:00+00:00", "close": 24500.0},
        {"timestamp": "2024-11-01 00:00:00+00:00", "close": 25000.0},
    ]).to_csv(exports_dir / "NIFTY_day.csv", index=False)

    result = load_daily_spot("NIFTY", date(2024, 10, 1), date(2024, 10, 31))
    assert len(result) == 1
    assert result.iloc[0]["close"] == 24500.0
