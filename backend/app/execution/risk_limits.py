"""Pure risk-limit checks.

Every function here is a real gate with a real reason string — none of
them rubber-stamp. Kept pure and stateless so each limit can be unit
tested in isolation and reasoned about without running the app.
"""

from dataclasses import dataclass, field
from datetime import time
from typing import Dict, List, Optional, Tuple

from backend.app.engines.algo_config import AlgoTradingConfig
from backend.app.market_data.lot_sizes import get_lot_size
from backend.app.strategies.cas_dislocation.models import CASDislocationConfig
from backend.app.strategies.order_flow_absorption.config import OFAOConfig


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
    # Algo capital/pyramid tracking (see check_capital_budget/check_lot_schedule).
    # Both reset only on process restart, same as the counters above — there
    # is no day-rollover mechanism anywhere in this engine yet.
    capital_deployed_today: float = 0.0
    fill_count_by_instrument: Dict[str, int] = field(default_factory=dict)


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


def check_algo_enabled(config: AlgoTradingConfig) -> Optional[str]:
    if not config.enabled:
        return "Algo trading is not enabled (configure and enable it from the Algo Dashboard)."
    return None


def _applies_to_configured_underlying(config: AlgoTradingConfig, instrument: str) -> bool:
    """The capital budget and pyramid schedule are scoped to exactly one
    underlying (the trader picks it when configuring MANUAL mode). A
    decision for any other instrument — a different automated strategy
    trading something else entirely — must not consume or be blocked by
    this budget. Matched by prefix since every decision's `instrument`
    string is built as "{underlying} {strike} {type}" or similar
    (verified across trending_oi_price_action, manual_trading) — a
    best-effort text match, not a guaranteed-robust instrument
    classification, since there's no shared structured instrument-type
    field across strategies today.
    """
    return bool(config.underlying) and instrument.startswith(config.underlying)


def check_capital_budget(
    config: AlgoTradingConfig, state: RiskState, instrument: str, quantity: int, price: float
) -> Optional[str]:
    """MANUAL mode only, and only for the configured underlying. Compares
    today's cumulative algo capital deployed (real submissions only —
    DRY_RUN/rejected never count, same rule as orders_placed_today) plus
    this order's value against the configured budget.
    """
    if config.mode != "MANUAL" or config.capital is None:
        return None
    if not _applies_to_configured_underlying(config, instrument):
        return None

    order_value = quantity * price
    projected = state.capital_deployed_today + order_value
    if projected > config.capital:
        return (
            f"Order value {order_value:.2f} would bring today's algo capital deployed to "
            f"{projected:.2f}, exceeding the configured budget of {config.capital:.2f}."
        )
    return None


def check_lot_schedule(
    config: AlgoTradingConfig,
    state: RiskState,
    instrument: str,
    instrument_key: str,
    quantity: int,
) -> Optional[str]:
    """MANUAL mode only, and only for the configured underlying. Enforces
    the pyramid tier schedule per instrument_key: the Nth fill may not
    exceed lot_schedule[N-1] lots (a cap, not an exact match — a strategy
    is free to buy fewer than the tier allows). fill_count_by_instrument
    tracks how many fills that instrument_key has already had; there is no
    per-position lifecycle here (see RiskState's own caveat) so this
    counts fills for the process's lifetime, not "since this position
    opened".
    """
    if config.mode != "MANUAL" or not config.lot_schedule:
        return None
    if not _applies_to_configured_underlying(config, instrument):
        return None

    lot_size = get_lot_size(config.underlying)  # underlying validated at configure() time
    fill_index = state.fill_count_by_instrument.get(instrument_key, 0)
    if fill_index >= len(config.lot_schedule):
        return (
            f"No pyramid tier configured for fill #{fill_index + 1} on {instrument_key} "
            f"(schedule has {len(config.lot_schedule)} tiers)."
        )

    max_lots = config.lot_schedule[fill_index]
    max_qty = max_lots * lot_size
    if quantity > max_qty:
        return (
            f"Tier {fill_index + 1} allows at most {max_lots} lots ({max_qty} qty) for "
            f"{instrument_key}, got {quantity}."
        )
    return None


def evaluate_algo_extra(
    config: AlgoTradingConfig,
    state: RiskState,
    instrument: str,
    instrument_key: str,
    quantity: int,
    price: float,
) -> Tuple[bool, List[str]]:
    """The additional checks applied only to ALGO-sourced decisions, on
    top of evaluate_all's universal checks. Kept separate so manual
    trading orders (which carry their own per-order sizing already) are
    never subject to a global capital budget or pyramid schedule meant for
    the automated strategies.
    """
    reasons = [
        reason
        for reason in (
            check_algo_enabled(config),
            check_capital_budget(config, state, instrument, quantity, price),
            check_lot_schedule(config, state, instrument, instrument_key, quantity),
        )
        if reason is not None
    ]
    return (not reasons), reasons


def check_cas_enabled(config: CASDislocationConfig) -> Optional[str]:
    """CAS Dislocation Engine's own arm switch — independent of the algo
    capital/pyramid gate (evaluate_algo_extra) and of manual trading.
    Applied only when a decision's source == "CAS_DISLOCATION".
    """
    if not config.enabled:
        return "CAS Dislocation Engine is not enabled (configure and enable it from its own page)."
    return None


def check_ofao_enabled(config: OFAOConfig) -> Optional[str]:
    """OFAO's own arm switch — same independent-gate pattern as
    check_cas_enabled, deliberately not sharing algo_config_state's
    single-underlying capital/pyramid budget (OFAO trades NIFTY and
    SENSEX concurrently — see the architecture doc §21). Applied only
    when a decision's source == "OFAO".
    """
    if not config.enabled:
        return "OFAO is not enabled (configure and enable it from its own page)."
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
