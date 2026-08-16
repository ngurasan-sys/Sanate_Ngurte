"""The OFAO state machine — spec §10. Exactly one active (non-terminal)
setup per instrument at a time; this is what makes "the strategy must not
generate multiple orders from the same setup" (spec §10/§42) structural
rather than a separate check bolted on afterward — engine.py cannot
start a new setup for an instrument while one is already in flight, full
stop, regardless of what the absorption/dominance modules report.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from .models import SetupContext, SetupDirection, SetupState, TERMINAL_STATES, TradeIntent, generate_setup_id

logger = logging.getLogger(__name__)


class InvalidTransitionError(Exception):
    """Raised when a transition is attempted from a state that cannot
    reach the requested state — this must never be silently allowed, or
    the "one setup = one signal" guarantee breaks.
    """


ALLOWED_TRANSITIONS: Dict[SetupState, Set[SetupState]] = {
    SetupState.NO_SETUP: {SetupState.LOCATION_APPROACHING, SetupState.LOCATION_REACHED},
    SetupState.LOCATION_APPROACHING: {SetupState.LOCATION_REACHED, SetupState.NO_SETUP},
    SetupState.LOCATION_REACHED: {SetupState.ABSORPTION_DETECTED, SetupState.NO_SETUP, SetupState.INVALIDATED},
    SetupState.ABSORPTION_DETECTED: {SetupState.WAITING_FOR_DOMINANCE, SetupState.INVALIDATED, SetupState.NO_SETUP},
    SetupState.WAITING_FOR_DOMINANCE: {SetupState.DOMINANCE_CONFIRMED, SetupState.INVALIDATED, SetupState.NO_SETUP},
    SetupState.DOMINANCE_CONFIRMED: {SetupState.SIGNAL_READY, SetupState.INVALIDATED},
    SetupState.SIGNAL_READY: {SetupState.ORDER_SUBMITTED, SetupState.CANCELLED},
    SetupState.ORDER_SUBMITTED: {SetupState.ORDER_FILLED, SetupState.CANCELLED},
    SetupState.ORDER_FILLED: {SetupState.POSITION_ACTIVE},
    SetupState.POSITION_ACTIVE: {SetupState.TARGET_1, SetupState.EXITED, SetupState.INVALIDATED},
    SetupState.TARGET_1: {SetupState.TARGET_2, SetupState.EXITED},
    SetupState.TARGET_2: {SetupState.EXITED},
    SetupState.EXITED: set(),      # terminal — reset() moves back to NO_SETUP explicitly
    SetupState.INVALIDATED: set(),
    SetupState.CANCELLED: set(),
}


class OFAOStateMachine:
    def __init__(self):
        self._contexts: Dict[str, SetupContext] = {}
        self._sequence_by_key: Dict[str, int] = {}  # keyed "{underlying}_{date}" per spec's daily-reset numbering

    def get(self, instrument: str) -> SetupContext:
        if instrument not in self._contexts:
            self._contexts[instrument] = SetupContext(instrument=instrument)
        return self._contexts[instrument]

    def has_active_setup(self, instrument: str) -> bool:
        """True whenever a setup is in flight (anything past NO_SETUP and
        not yet terminal) — the actual duplicate-setup guard.
        """
        state = self.get(instrument).state
        return state != SetupState.NO_SETUP and state not in TERMINAL_STATES

    def transition(
        self, instrument: str, new_state: SetupState, now: Optional[datetime] = None, **field_updates,
    ) -> SetupContext:
        ctx = self.get(instrument)
        now = now or datetime.now(timezone.utc)

        allowed = ALLOWED_TRANSITIONS.get(ctx.state, set())
        if new_state not in allowed:
            raise InvalidTransitionError(
                f"{instrument}: cannot transition {ctx.state.value} -> {new_state.value} "
                f"(allowed from {ctx.state.value}: {sorted(s.value for s in allowed)})."
            )

        # setup_id is minted exactly once, the first time a setup gets a
        # known direction (LOCATION_REACHED) — every later transition for
        # this same setup keeps the same id.
        if new_state == SetupState.LOCATION_REACHED and ctx.setup_id is None:
            direction = field_updates.get("direction")
            if not isinstance(direction, SetupDirection):
                raise ValueError("LOCATION_REACHED requires a SetupDirection in field_updates['direction'].")
            key = f"{instrument}_{now.strftime('%Y-%m-%d')}"
            self._sequence_by_key[key] = self._sequence_by_key.get(key, 0) + 1
            ctx.setup_id = generate_setup_id(instrument.split(" ")[0], now, direction, self._sequence_by_key[key])
            ctx.created_at = now

        old_state = ctx.state
        for field_name, value in field_updates.items():
            setattr(ctx, field_name, value)

        ctx.state = new_state
        ctx.state_entered_at = now

        if new_state == SetupState.SIGNAL_READY:
            ctx.signal_ready_at = now

        logger.info("%s %s -> %s (setup_id=%s)", instrument, old_state.value, new_state.value, ctx.setup_id)
        return ctx

    def reset(self, instrument: str, reason: str, now: Optional[datetime] = None) -> SetupContext:
        """Explicit terminal -> NO_SETUP reset, ready for the next setup
        on this instrument. Only valid from a terminal state — resetting
        mid-flight would be exactly the kind of silent state loss this
        machine exists to prevent.
        """
        ctx = self.get(instrument)
        if ctx.state not in TERMINAL_STATES and ctx.state != SetupState.NO_SETUP:
            raise InvalidTransitionError(
                f"{instrument}: cannot reset from non-terminal state {ctx.state.value}."
            )
        now = now or datetime.now(timezone.utc)
        logger.info("%s reset from %s (setup_id=%s): %s", instrument, ctx.state.value, ctx.setup_id, reason)
        self._contexts[instrument] = SetupContext(instrument=instrument)
        return self._contexts[instrument]

    def active_setups(self) -> List[str]:
        """Instrument keys with a setup currently in flight (past NO_SETUP,
        not yet terminal). The single public source for "what is active" —
        callers must not walk _contexts themselves.
        """
        return [
            instrument
            for instrument, ctx in self._contexts.items()
            if ctx.state != SetupState.NO_SETUP and ctx.state not in TERMINAL_STATES
        ]

    def has_any_active_setup(self) -> bool:
        return bool(self.active_setups())

    def is_signal_stale(self, instrument: str, timeout_seconds: float, now: Optional[datetime] = None) -> bool:
        """Spec §23 — a SIGNAL_READY setup not executed within
        signal_timeout_seconds must be revalidated, not blindly executed.
        """
        ctx = self.get(instrument)
        if ctx.state != SetupState.SIGNAL_READY or ctx.signal_ready_at is None:
            return False
        now = now or datetime.now(timezone.utc)
        return (now - ctx.signal_ready_at).total_seconds() > timeout_seconds
