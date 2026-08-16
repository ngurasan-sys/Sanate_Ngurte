"""End-to-end test of the real pipeline: Parquet + CSV on disk ->
data_loader -> selection -> strategy -> actual vectorbt Portfolio ->
BacktestResult. Uses tiny synthetic data (not the real multi-GB export)
written to a temp dir, with config paths monkeypatched to point there —
proves the wiring works, not vectorbt's own internals (already smoke-
tested manually against this Python/numba combination).
"""

from datetime import date

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from backend.app.backtest import data_loader as data_loader_module
from backend.app.backtest.engine import run_backtest
from backend.app.backtest.models import BacktestRequest


def _write_synthetic_dataset(tmp_path):
    oi_dir = tmp_path / "oi_parquet" / "NIFTY" / "year_month=2024-10"
    oi_dir.mkdir(parents=True)

    rows = []
    strikes = [24400, 24450, 24500, 24550, 24600]
    # Days 1-2 are unchanged from the original two-day fixture (kept that
    # way so test_run_backtest_end_to_end's strike-24500-both-days
    # assumption still holds). Days 3-4 are added purely for the momentum
    # strategies: spot goes 24500(day2) -> 24700(day3) -> 24500(day4), an
    # "UP" move between day2 and day3 that labels day4's *entry* direction
    # as "UP" per compute_daily_entry_direction (day4's own close is
    # irrelevant to its own label). Days 1-2 stay unlabeled (no prior pair).
    for day_offset, base_premium in [(1, 100.0), (2, 60.0), (3, 80.0), (4, 80.0)]:
        day = f"2024-10-0{day_offset}"
        for minute in range(20):
            ts = pd.Timestamp(f"{day} 09:{15 + minute:02d}:00")
            drift = -2.0 * minute if day_offset == 2 else 0.5 * minute  # day2 down (win for a short), others drift up
            for strike in strikes:
                for option_type, base in (("CE", base_premium / 2), ("PE", base_premium / 2)):
                    rows.append({
                        "timestamp": ts, "symbol": "NIFTY", "strike": float(strike), "option_type": option_type,
                        "open": base, "high": base, "low": base,
                        "close": max(base + drift, 1.0), "volume": 1000, "oi": 10000,
                    })

    df = pd.DataFrame(rows)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, oi_dir / "data.parquet")

    day_csv = tmp_path / "exports" / "NIFTY_day.csv"
    day_csv.parent.mkdir(parents=True)
    pd.DataFrame([
        {"timestamp": "2024-10-01 00:00:00+00:00", "symbol": "NIFTY", "open": 24500, "high": 24500, "low": 24500, "close": 24500.0, "volume": 100},
        {"timestamp": "2024-10-02 00:00:00+00:00", "symbol": "NIFTY", "open": 24500, "high": 24500, "low": 24500, "close": 24500.0, "volume": 100},
        {"timestamp": "2024-10-03 00:00:00+00:00", "symbol": "NIFTY", "open": 24500, "high": 24500, "low": 24500, "close": 24700.0, "volume": 100},
        {"timestamp": "2024-10-04 00:00:00+00:00", "symbol": "NIFTY", "open": 24500, "high": 24500, "low": 24500, "close": 24500.0, "volume": 100},
    ]).to_csv(day_csv, index=False)

    return tmp_path / "oi_parquet", tmp_path / "exports"


@pytest.fixture
def synthetic_data(tmp_path, monkeypatch):
    oi_dir, exports_dir = _write_synthetic_dataset(tmp_path)
    monkeypatch.setattr(data_loader_module, "OI_PARQUET_DIR", oi_dir)
    monkeypatch.setattr(data_loader_module, "RAW_EXPORTS_DIR", exports_dir)
    return oi_dir, exports_dir


def test_run_backtest_end_to_end(synthetic_data):
    request = BacktestRequest(
        underlying="NIFTY", date_from=date(2024, 10, 1), date_to=date(2024, 10, 2),
        stop_loss_pct=50.0, target_pct=30.0, entry_minutes_after_open=2, exit_minutes_before_close=2,
    )

    result = run_backtest(request)

    assert result.underlying == "NIFTY"
    assert result.initial_cash == 100_000.0
    assert len(result.equity_curve) > 0
    assert result.total_trades >= 1
    # ATM strike 24500 (spot=24500.0) should be the one selected both days.
    assert all(t.strike == 24500.0 for t in result.trades)


def test_run_backtest_raises_for_unsupported_underlying(synthetic_data):
    request = BacktestRequest(underlying="FINNIFTY", date_from=date(2024, 10, 1), date_to=date(2024, 10, 2))
    with pytest.raises(Exception):
        run_backtest(request)


def test_run_backtest_raises_when_no_data_in_range(synthetic_data):
    request = BacktestRequest(underlying="NIFTY", date_from=date(2025, 1, 1), date_to=date(2025, 1, 2))
    with pytest.raises(Exception):
        run_backtest(request)


def test_run_backtest_rejects_unknown_strategy_at_request_construction(synthetic_data):
    with pytest.raises(Exception):
        BacktestRequest(underlying="NIFTY", date_from=date(2024, 10, 1), date_to=date(2024, 10, 2), strategy="NOT_REAL")


def test_run_backtest_long_straddle_trades_every_day(synthetic_data):
    request = BacktestRequest(
        underlying="NIFTY", date_from=date(2024, 10, 1), date_to=date(2024, 10, 2), strategy="LONG_STRADDLE",
        stop_loss_pct=50.0, target_pct=30.0, entry_minutes_after_open=2, exit_minutes_before_close=2,
    )
    result = run_backtest(request)
    assert result.total_trades == 2  # both days trade, same as SHORT_STRADDLE on this fixture


def test_run_backtest_long_ce_momentum_only_trades_the_up_labeled_day(synthetic_data):
    request = BacktestRequest(
        underlying="NIFTY", date_from=date(2024, 10, 1), date_to=date(2024, 10, 4), strategy="LONG_CE_MOMENTUM",
        stop_loss_pct=50.0, target_pct=30.0, entry_minutes_after_open=2, exit_minutes_before_close=2,
    )
    result = run_backtest(request)

    assert result.total_trades == 1
    assert result.trades[0].entry_time.date() == date(2024, 10, 4)
    assert result.trades[0].strike == 24500.0


def test_run_backtest_long_pe_momentum_finds_no_up_days_and_places_no_trades(synthetic_data):
    # This fixture never produces a "DOWN" label, so LONG_PE_MOMENTUM
    # should complete with zero trades rather than raising.
    request = BacktestRequest(
        underlying="NIFTY", date_from=date(2024, 10, 1), date_to=date(2024, 10, 4), strategy="LONG_PE_MOMENTUM",
        stop_loss_pct=50.0, target_pct=30.0, entry_minutes_after_open=2, exit_minutes_before_close=2,
    )
    result = run_backtest(request)

    assert result.total_trades == 0
    assert result.win_rate_pct is None
    assert result.final_equity == pytest.approx(result.initial_cash)
