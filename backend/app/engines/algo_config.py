"""Algo trading capital/sizing configuration — the automated-strategy
counterpart to manual_trading's per-order lots/SL/target, but scoped
globally rather than per-order since the algo engines (gap_opening,
trending_oi_price_action, etc.) generate their own signals independently.

SYSTEM mode: automated strategies run under RiskEngine's existing
defaults only (quantity/position/loss/order caps) — no capital budget or
pyramid tier schedule enforced.

MANUAL mode: the trader sets a capital budget and a pyramid tier lot
schedule (first buy N lots, second add M lots, ...) for one underlying.
RiskEngine enforces both on every ALGO-sourced decision (see
risk_limits.check_capital_budget / check_lot_schedule) — manual trading
orders are untouched, they carry their own per-order sizing already.

`enabled` is a real gate, not cosmetic: while False, every ALGO-sourced
decision is rejected by RiskEngine regardless of mode. This is
independent of the broker-level LIVE arm switch (execution.runtime_state)
— that one gates whether an approved order reaches a real broker; this
one gates whether an automated decision is even considered for approval.

Stop-loss/target percentages are stored and surfaced to the frontend, but
are NOT enforced on automated positions — each strategy manages its own
exit logic internally (see the "Global risk gate only" scope decision:
rewiring every strategy to read a shared SL/target would mean editing
gap_opening, trending_oi_price_action, oh_ol, atr, etc. independently,
each built and tuned on its own). Surfacing a number here that silently
does nothing would be worse than not having it — so callers must never
imply these percentages stop a losing automated trade today.
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


class AlgoTradingConfig(BaseModel):
    mode: Literal["SYSTEM", "MANUAL"] = "SYSTEM"
    enabled: bool = False
    underlying: Optional[str] = None       # NIFTY | BANKNIFTY | SENSEX — required for MANUAL mode
    capital: Optional[float] = None        # total ₹ budget for algo trading, MANUAL mode only
    lot_schedule: List[int] = []           # [tier1_lots, tier2_lots, tier3_lots, ...], MANUAL mode only
    stop_loss_pct: Optional[float] = None  # informational only — see module docstring
    target_pct: Optional[float] = None     # informational only — see module docstring
    updated_at: Optional[datetime] = None


class AlgoConfigError(Exception):
    """Raised when a configure/enable request is invalid."""


class AlgoConfigState:
    """In-memory holder, same pattern as execution.runtime_state — resets
    to SYSTEM/disabled on process restart, deliberately: nobody should be
    able to leave a capital-armed automated config active across a deploy
    or crash by accident.
    """

    def __init__(self):
        self._config = AlgoTradingConfig()

    def get(self) -> AlgoTradingConfig:
        return self._config

    def configure(
        self,
        mode: Literal["SYSTEM", "MANUAL"],
        underlying: Optional[str] = None,
        capital: Optional[float] = None,
        lot_schedule: Optional[List[int]] = None,
        stop_loss_pct: Optional[float] = None,
        target_pct: Optional[float] = None,
    ) -> AlgoTradingConfig:
        lot_schedule = lot_schedule or []

        if mode == "MANUAL":
            if not underlying:
                raise AlgoConfigError("MANUAL mode requires an underlying (NIFTY/BANKNIFTY/SENSEX).")
            if capital is None or capital <= 0:
                raise AlgoConfigError("MANUAL mode requires a positive capital budget.")
            if not lot_schedule:
                raise AlgoConfigError("MANUAL mode requires at least one pyramid tier (lot_schedule).")
            if any(lots <= 0 for lots in lot_schedule):
                raise AlgoConfigError("Every tier in lot_schedule must be a positive number of lots.")
            if stop_loss_pct is not None and stop_loss_pct <= 0:
                raise AlgoConfigError("stop_loss_pct must be positive (a % drawdown, e.g. 30 for -30%).")
            if target_pct is not None and target_pct <= 0:
                raise AlgoConfigError("target_pct must be positive (a % gain, e.g. 50 for +50%).")

        # Switching to SYSTEM (or reconfiguring) always disarms first — a
        # config change must never silently keep capital deployment armed
        # under different numbers than the trader last saw confirmed.
        self._config = AlgoTradingConfig(
            mode=mode,
            enabled=False,
            underlying=underlying if mode == "MANUAL" else None,
            capital=capital if mode == "MANUAL" else None,
            lot_schedule=lot_schedule if mode == "MANUAL" else [],
            stop_loss_pct=stop_loss_pct if mode == "MANUAL" else None,
            target_pct=target_pct if mode == "MANUAL" else None,
            updated_at=datetime.now(),
        )
        return self._config

    def enable(self) -> AlgoTradingConfig:
        self._config.enabled = True
        return self._config

    def disable(self) -> AlgoTradingConfig:
        self._config.enabled = False
        return self._config


algo_config_state = AlgoConfigState()
