from datetime import time

import pytest

from backend.app.execution.risk_limits import (
    RiskLimits,
    RiskState,
    check_daily_loss,
    check_daily_order_count,
    check_kill_switch,
    check_market_hours,
    check_open_positions,
    check_quantity,
    evaluate_all,
)

MID_SESSION = time(11, 0)


def test_kill_switch_blocks_when_trading_disabled():
    assert check_kill_switch(RiskLimits(allow_trading=False), RiskState()) is not None


def test_kill_switch_blocks_when_halted():
    reason = check_kill_switch(RiskLimits(), RiskState(halted_reason="manual halt"))
    assert "manual halt" in reason


def test_kill_switch_passes_normally():
    assert check_kill_switch(RiskLimits(), RiskState()) is None


def test_market_hours_blocks_before_open():
    assert check_market_hours(RiskLimits(), time(9, 0)) is not None


def test_market_hours_blocks_at_and_after_close():
    assert check_market_hours(RiskLimits(), time(15, 30)) is not None
    assert check_market_hours(RiskLimits(), time(16, 0)) is not None


def test_market_hours_passes_during_session():
    assert check_market_hours(RiskLimits(), MID_SESSION) is None
    assert check_market_hours(RiskLimits(), time(9, 15)) is None


def test_quantity_rejects_zero_and_negative():
    assert check_quantity(RiskLimits(), 0) is not None
    assert check_quantity(RiskLimits(), -5) is not None


def test_quantity_rejects_above_cap():
    assert check_quantity(RiskLimits(max_quantity_per_order=50), 51) is not None


def test_quantity_passes_at_cap():
    assert check_quantity(RiskLimits(max_quantity_per_order=50), 50) is None


def test_open_positions_blocks_at_cap():
    limits = RiskLimits(max_open_positions=2)
    assert check_open_positions(limits, RiskState(open_positions=2)) is not None


def test_open_positions_passes_below_cap():
    limits = RiskLimits(max_open_positions=2)
    assert check_open_positions(limits, RiskState(open_positions=1)) is None


def test_daily_loss_blocks_at_limit():
    limits = RiskLimits(max_daily_loss=5000)
    assert check_daily_loss(limits, RiskState(realized_pnl_today=-5000)) is not None
    assert check_daily_loss(limits, RiskState(realized_pnl_today=-6000)) is not None


def test_daily_loss_passes_when_profitable_or_small_loss():
    limits = RiskLimits(max_daily_loss=5000)
    assert check_daily_loss(limits, RiskState(realized_pnl_today=2000)) is None
    assert check_daily_loss(limits, RiskState(realized_pnl_today=-100)) is None


def test_daily_order_count_blocks_at_cap():
    limits = RiskLimits(max_daily_orders=3)
    assert check_daily_order_count(limits, RiskState(orders_placed_today=3)) is not None


def test_evaluate_all_approves_clean_state():
    approved, reasons = evaluate_all(RiskLimits(), RiskState(), quantity=10, now=MID_SESSION)
    assert approved is True
    assert reasons == []


def test_evaluate_all_returns_every_failing_reason_not_just_first():
    """A caller fixing one limit should see the others immediately."""
    limits = RiskLimits(max_quantity_per_order=10, max_open_positions=1, max_daily_loss=100)
    state = RiskState(open_positions=5, realized_pnl_today=-500)

    approved, reasons = evaluate_all(limits, state, quantity=999, now=time(3, 0))

    assert approved is False
    assert len(reasons) >= 4  # hours + quantity + positions + daily loss


def test_evaluate_all_rejects_when_only_one_limit_fails():
    approved, reasons = evaluate_all(
        RiskLimits(), RiskState(), quantity=10, now=time(16, 0),
    )
    assert approved is False
    assert len(reasons) == 1
