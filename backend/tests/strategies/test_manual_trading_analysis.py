import pytest

from backend.app.strategies.manual_trading.analysis import (
    compute_weighted_entry_price,
    extract_leg,
    resolve_strike_row,
    should_exit,
)


def _row(strike, call_key="CE1", put_key="PE1"):
    # instrument_key is a sibling of market_data in the real Upstox
    # response (verified live against the actual API), not nested inside it.
    return {
        "strike_price": strike,
        "call_options": {"instrument_key": call_key, "market_data": {"ltp": 100.0}},
        "put_options": {"instrument_key": put_key, "market_data": {"ltp": 90.0}},
    }


CHAIN = [_row(24400), _row(24500), _row(24600)]


def test_resolve_strike_row_exact_match():
    row = resolve_strike_row(CHAIN, 24500)
    assert row["strike_price"] == 24500


def test_resolve_strike_row_nearest_when_no_exact_match():
    row = resolve_strike_row(CHAIN, 24530)
    assert row["strike_price"] == 24500


def test_resolve_strike_row_empty_chain_returns_none():
    assert resolve_strike_row([], 24500) is None


def test_extract_leg_call_and_put():
    row = _row(24500, call_key="CE_X", put_key="PE_X")
    assert extract_leg(row, "CE")["instrument_key"] == "CE_X"
    assert extract_leg(row, "PE")["instrument_key"] == "PE_X"


def test_compute_weighted_entry_price():
    # 10 units @ 100, add 10 units @ 120 -> average 110
    assert compute_weighted_entry_price(10, 100.0, 10, 120.0) == pytest.approx(110.0)


def test_compute_weighted_entry_price_zero_total_qty_returns_zero():
    assert compute_weighted_entry_price(0, 0.0, 0, 100.0) == 0.0


def test_should_exit_below_stop_loss():
    assert should_exit(ltp=40.0, stop_loss=50.0, target=150.0) == "STOP_LOSS_HIT"


def test_should_exit_at_stop_loss_boundary():
    assert should_exit(ltp=50.0, stop_loss=50.0, target=150.0) == "STOP_LOSS_HIT"


def test_should_exit_above_target():
    assert should_exit(ltp=160.0, stop_loss=50.0, target=150.0) == "TARGET_HIT"


def test_should_exit_at_target_boundary():
    assert should_exit(ltp=150.0, stop_loss=50.0, target=150.0) == "TARGET_HIT"


def test_should_exit_none_within_range():
    assert should_exit(ltp=100.0, stop_loss=50.0, target=150.0) is None


def test_should_exit_checks_stop_loss_before_target():
    # A valid position always has stop_loss < target (enforced at order
    # placement), so with real data the two conditions can never both be
    # true at once — this just documents the check order for an inverted,
    # engine-rejected config, without implying it's a reachable scenario.
    assert should_exit(ltp=200.0, stop_loss=150.0, target=100.0) == "TARGET_HIT"
    assert should_exit(ltp=120.0, stop_loss=150.0, target=100.0) == "STOP_LOSS_HIT"
