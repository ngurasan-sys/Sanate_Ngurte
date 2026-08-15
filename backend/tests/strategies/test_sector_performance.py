import pytest

from backend.app.market_data.index_constituents import IndexConstituent, NIFTY50_TOP10
from backend.app.strategies.option_analytics.sector_performance import (
    compute_sector_returns,
    rank_sectors,
)


def test_compute_sector_returns_weighted_average_within_sector():
    universe = [
        IndexConstituent(symbol="A", name="A", weight=0.10, sector="Financial Services"),
        IndexConstituent(symbol="B", name="B", weight=0.05, sector="Financial Services"),
        IndexConstituent(symbol="C", name="C", weight=0.08, sector="Information Technology"),
    ]
    returns = {"A": 0.02, "B": -0.01, "C": 0.05}

    result = compute_sector_returns(returns, universe)

    # Financial Services: (0.10*0.02 + 0.05*-0.01) / (0.10+0.05) = 0.0015/0.15
    assert result["Financial Services"] == pytest.approx(0.0015 / 0.15)
    assert result["Information Technology"] == pytest.approx(0.05)


def test_compute_sector_returns_skips_missing_symbols():
    universe = [
        IndexConstituent(symbol="A", name="A", weight=0.10, sector="Financial Services"),
        IndexConstituent(symbol="B", name="B", weight=0.05, sector="Financial Services"),
    ]
    returns = {"A": 0.02}  # B missing — its tick hasn't arrived

    result = compute_sector_returns(returns, universe)
    # Only A counted -> sector return equals A's return exactly, not
    # diluted by treating B as a zero.
    assert result["Financial Services"] == pytest.approx(0.02)


def test_compute_sector_returns_empty_when_no_returns_supplied():
    result = compute_sector_returns({}, NIFTY50_TOP10)
    assert result == {}


def test_rank_sectors_best_first():
    sector_returns = {"IT": 0.03, "Financials": -0.01, "Energy": 0.05}
    ranked = rank_sectors(sector_returns)
    assert ranked == [("Energy", 0.05), ("IT", 0.03), ("Financials", -0.01)]


def test_real_nifty_universe_spans_multiple_sectors():
    # NIFTY50_TOP10 is genuinely multi-sector — the point of building this
    # module at all. BANKNIFTY_TOP7 is entirely Financial Services by
    # construction, so it isn't exercised here.
    returns = {c.symbol: 0.01 for c in NIFTY50_TOP10}
    result = compute_sector_returns(returns, NIFTY50_TOP10)
    assert len(result) >= 5
    assert all(v == pytest.approx(0.01) for v in result.values())
