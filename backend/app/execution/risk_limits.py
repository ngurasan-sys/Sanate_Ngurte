"""Pure risk-limit checks.

Every function here is a real gate with a real reason string — none of
them rubber-stamp. Kept pure and stateless so each limit can be unit
tested in isolation and reasoned about without running the app.
"""

from dataclasses import dataclass, field
from datetime import time
from typing import Dict, List, Optional, Tuple


@dataclass
class RiskLimits:
    """Hard limits. Defaults are deliberately conservative — widen them
    consciously, don't inherit a permissive default by accident.
    """

    max_quantity_per_order: int = 100
    max_open_positions: int = 3
    max_daily_loss: float = 5000.0        # absolute currency, positive number
    max_daily_orders: int = 20
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    allow_trading: bool = True            # global kill switch


@dataclass
class RiskState:
    """Live counters the limits are checked against."""

    open_positions: int = 0
    realized_pnl_today: float = 0.0       # negative means a loss
    orders_placed_today: int = 0
    halted_reason: Optional[str] = None


def check_kill_switch(limits: RiskLimits, state: RiskState) -> Optional[str]:
    if not limits.allow_trading:
        return "Trading is disabled by the global kill switch (allow_trading=False)."
    if state.halted_reason:
        return f"Trading halted: {state.halted_reason}"
    return None


def check_market_hours(limits: RiskLimits, now: time) -> Optional[str]:
    if now < limits.market_open:
        return f"Market not open yet (opens {limits.market_open.strftime('%H:%M')})."
    if now >= limits.market_close:
        return f"Market closed (closes {limits.market_close.strftime('%H:%M')})."
    return None


def check_quantity(limits: RiskLimits, quantity: int) -> Optional[str]:
    if quantity <= 0:
        return f"Invalid quantity {quantity} — must be positive."
    if quantity > limits.max_quantity_per_order:
        return (
            f"Quantity {quantity} exceeds max_quantity_per_order "
            f"({limits.max_quantity_per_order})."
        )
    return None


def check_open_positions(limits: RiskLimits, state: RiskState) -> Optional[str]:
    if state.open_positions >= limits.max_open_positions:
        return (
            f"Already holding {state.open_positions} open positions "
            f"(max {limits.max_open_positions})."
        )
    return None


def check_daily_loss(limits: RiskLimits, state: RiskState) -> Optional[str]:
    if state.realized_pnl_today <= -abs(limits.max_daily_loss):
        return (
            f"Daily loss limit hit: realized P&L {state.realized_pnl_today:.2f} "
            f"has reached the {-abs(limits.max_daily_loss):.2f} limit."
        )
    return None


def check_daily_order_count(limits: RiskLimits, state: RiskState) -> Optional[str]:
    if state.orders_placed_today >= limits.max_daily_orders:
        return (
            f"Daily order cap reached ({state.orders_placed_today}/"
            f"{limits.max_daily_orders})."
        )
    return None


def evaluate_all(
    limits: RiskLimits,
    state: RiskState,
    quantity: int,
    now: time,
) -> Tuple[bool, List[str]]:
    """Runs every check. Returns (approved, reasons).

    ALL failing reasons are returned, not just the first — a caller
    fixing one limit should be able to see the others immediately rather
    than rediscovering them one rejection at a time.
    """
    reasons = [
        reason
        for reason in (
            check_kill_switch(limits, state),
            check_market_hours(limits, now),
            check_quantity(limits, quantity),
            check_open_positions(limits, state),
            check_daily_loss(limits, state),
            check_daily_order_count(limits, state),
        )
        if reason is not None
    ]
    return (not reasons), reasons
