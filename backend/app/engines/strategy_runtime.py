"""Canonical per-strategy runtime state — start/stop, execution_mode
(DISABLED/PAPER/ALGO), trading_mode (AUTO/MANUAL) — for every strategy in
the registry (backend/app/api/endpoints/strategies.py).

Why this exists as its own module rather than extending algo_config_state/
cas_config_state/ofao_engine.config: those three are explicitly documented
as intentionally NOT persisted (a capital-armed config must not survive a
crash/deploy by accident — see their own docstrings). Per-strategy
enabled/execution_mode/trading_mode is a different kind of state — an
operator's day-to-day "which strategies are on" configuration — and DOES
need to survive a restart, the same way active_broker.py's broker
selection does. This module follows that exact precedent: a flat JSON
file next to it, read on first access, written on every change.

Mutual exclusivity is enforced here, not just in the frontend:
- execution_mode is a single enum (DISABLED | PAPER | ALGO), never two
  independent booleans — so "ALGO on AND PAPER on" is structurally
  impossible to represent, let alone reach.
- trading_mode is a single enum (AUTO | MANUAL), same reasoning.

This module does NOT gate decisions itself — RiskEngine does, by calling
is_strategy_permitted() (mirrors the existing check_algo_enabled /
check_cas_enabled / check_ofao_enabled precedent in risk_limits.py) before
approving a decision. This module is the source of truth those checks
read; it has no opinion on risk/execution logic itself.
"""

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Literal, Optional

from backend.app.core.event_bus import event_bus

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_PATH = _BACKEND_ROOT / ".strategy_runtime.json"

ExecutionMode = Literal["DISABLED", "PAPER", "ALGO"]
TradingMode = Literal["AUTO", "MANUAL"]
StrategyStatus = Literal[
    "OFF", "STARTING", "READY", "RUNNING", "SIGNAL", "POSITION_ACTIVE",
    "STOPPING", "BLOCKED", "ERROR", "DISCONNECTED", "DATA_STALE",
]


class StrategyControlError(Exception):
    """Raised when a start/stop/mode-change request is invalid or the
    strategy fails a readiness check."""


@dataclass
class StrategyRuntimeState:
    strategy_id: str
    enabled: bool = False
    execution_mode: ExecutionMode = "DISABLED"
    trading_mode: TradingMode = "AUTO"
    status: StrategyStatus = "OFF"
    blocked_reason: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class StrategyRuntimeRegistry:
    """One StrategyRuntimeState per registered strategy_id, persisted as a
    flat JSON file (same pattern as active_broker.py's STATE_PATH)."""

    def __init__(self):
        self._states: Dict[str, StrategyRuntimeState] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not STATE_PATH.exists():
            return
        try:
            raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read %s — starting with empty strategy runtime state.", STATE_PATH)
            return
        for strategy_id, payload in raw.items():
            try:
                self._states[strategy_id] = StrategyRuntimeState(**payload)
            except TypeError:
                logger.warning("Skipping malformed persisted state for %r", strategy_id)

    def _persist(self) -> None:
        payload = {sid: s.to_dict() for sid, s in self._states.items()}
        STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get(self, strategy_id: str) -> StrategyRuntimeState:
        self._ensure_loaded()
        if strategy_id not in self._states:
            self._states[strategy_id] = StrategyRuntimeState(strategy_id=strategy_id)
        return self._states[strategy_id]

    def get_all(self) -> Dict[str, StrategyRuntimeState]:
        self._ensure_loaded()
        return dict(self._states)

    def _touch_and_persist(self, state: StrategyRuntimeState) -> StrategyRuntimeState:
        state.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist()
        payload = {"strategy_id": state.strategy_id, **state.to_dict()}
        try:
            asyncio.create_task(event_bus.publish("STRATEGY_CONFIG_CHANGED", payload))
        except RuntimeError:
            # No running event loop (e.g. called from a sync test) — state
            # is still persisted/updated, just not broadcast. Matches
            # websockets.py's _publish_model_or_dict fire-and-forget style.
            logger.debug("No event loop running; skipping STRATEGY_CONFIG_CHANGED broadcast.")
        return state

    def set_execution_mode(self, strategy_id: str, mode: ExecutionMode) -> StrategyRuntimeState:
        """DISABLED/PAPER/ALGO is a single field, not two booleans — setting
        it to ALGO structurally disables PAPER and vice versa; there is no
        way to represent both at once."""
        state = self.get(strategy_id)
        state.execution_mode = mode
        if mode == "DISABLED":
            state.enabled = False
            if state.status not in ("POSITION_ACTIVE",):
                state.status = "OFF"
        return self._touch_and_persist(state)

    def set_trading_mode(self, strategy_id: str, mode: TradingMode) -> StrategyRuntimeState:
        state = self.get(strategy_id)
        state.trading_mode = mode
        return self._touch_and_persist(state)

    def mark_started(self, strategy_id: str) -> StrategyRuntimeState:
        state = self.get(strategy_id)
        state.enabled = True
        state.status = "RUNNING"
        state.blocked_reason = None
        return self._touch_and_persist(state)

    def mark_stopped(self, strategy_id: str, *, has_open_position: bool) -> StrategyRuntimeState:
        """STOP only blocks NEW entries — enabled=False is what RiskEngine's
        per-strategy gate reads. It never touches an open position; that
        stays under existing exit management regardless of this flag."""
        state = self.get(strategy_id)
        state.enabled = False
        state.status = "POSITION_ACTIVE" if has_open_position else "OFF"
        return self._touch_and_persist(state)

    def mark_blocked(self, strategy_id: str, reason: str) -> StrategyRuntimeState:
        state = self.get(strategy_id)
        state.enabled = False
        state.status = "BLOCKED"
        state.blocked_reason = reason
        return self._touch_and_persist(state)

    def is_strategy_permitted(self, strategy_id: str) -> Optional[str]:
        """Mirrors check_algo_enabled/check_cas_enabled/check_ofao_enabled
        in risk_limits.py — returns None if the strategy may submit new
        decisions, or a rejection reason string if not. Called by
        RiskEngine per strategy_id, independent of execution_mode value
        (DISABLED always blocks; PAPER/ALGO only block if not enabled)."""
        self._ensure_loaded()
        state = self._states.get(strategy_id)
        if state is None:
            # Never explicitly configured via this registry — legacy
            # strategies with no per-strategy control yet are NOT gated
            # here (unchanged behavior from before this module existed).
            return None
        if state.execution_mode == "DISABLED" or not state.enabled:
            return f"{strategy_id} is not enabled (start it from the Algo Dashboard)."
        return None


strategy_runtime = StrategyRuntimeRegistry()
