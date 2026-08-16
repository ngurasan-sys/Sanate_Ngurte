"""State enum, setup context, TradeIntent — spec §10/§36.

setup_id is the mechanism spec §10/§42 relies on to guarantee "one setup
= one signal, never multiple orders from the same setup" — see
state_machine.py, which is the only thing allowed to create/advance one.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel


class SetupState(str, Enum):
    NO_SETUP = "NO_SETUP"
    LOCATION_APPROACHING = "LOCATION_APPROACHING"
    LOCATION_REACHED = "LOCATION_REACHED"
    ABSORPTION_DETECTED = "ABSORPTION_DETECTED"
    WAITING_FOR_DOMINANCE = "WAITING_FOR_DOMINANCE"
    DOMINANCE_CONFIRMED = "DOMINANCE_CONFIRMED"
    SIGNAL_READY = "SIGNAL_READY"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_FILLED = "ORDER_FILLED"
    POSITION_ACTIVE = "POSITION_ACTIVE"
    TARGET_1 = "TARGET_1"
    TARGET_2 = "TARGET_2"
    EXITED = "EXITED"
    INVALIDATED = "INVALIDATED"
    CANCELLED = "CANCELLED"


# Terminal states a fresh setup can start from — reaching any of these
# always eventually resets back to NO_SETUP (state_machine.py's job).
TERMINAL_STATES = frozenset({SetupState.EXITED, SetupState.INVALIDATED, SetupState.CANCELLED})

# Once past this point, a real trade instruction may have been sent — the
# risk/execution safety checks (spec §22/§42) get stricter from here on.
ORDER_LIFECYCLE_STATES = frozenset({
    SetupState.ORDER_SUBMITTED, SetupState.ORDER_FILLED, SetupState.POSITION_ACTIVE,
    SetupState.TARGET_1, SetupState.TARGET_2,
})


class SetupDirection(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"


def generate_setup_id(underlying: str, timestamp: datetime, direction: SetupDirection, sequence: int) -> str:
    """e.g. NIFTY_2026-08-16_094812_BULL_001 — the exact format from spec §10."""
    date_str = timestamp.strftime("%Y-%m-%d")
    time_str = timestamp.strftime("%H%M%S")
    return f"{underlying}_{date_str}_{time_str}_{direction.value}_{sequence:03d}"


class TradeIntent(BaseModel):
    """The standardized object this strategy hands to the existing
    risk/execution pipeline — spec §36. Nothing in this object, or in
    whatever produces it, may branch on LIVE vs PAPER (spec §35);
    order_gateway.resolve_mode() decides that, entirely downstream of
    this object's existence.
    """
    strategy_name: str = "ORDER_FLOW_ABSORPTION_OPTIONS"
    setup_id: str
    timestamp: datetime
    underlying: str
    direction: str            # "BUY" (options are always bought long in this strategy)
    option_type: str          # "CE" | "PE"
    strike: float
    expiry: str
    quantity: int
    underlying_trigger: float
    underlying_stop: float
    underlying_target: float
    risk_reward: float
    score: int
    score_max: int = 14       # 14 conditions listed across spec §11/§12
    confidence: str           # e.g. "A+"
    reason: str
    location: str
    absorption_strength: float
    imbalance_ratio_pct: float
    market_regime: str = "UNKNOWN"
    volatility_regime: str = "UNKNOWN"
    # Filled in by _resolve_and_submit once the option chain lookup
    # resolves a real tradable contract — None until then, since the
    # signal itself is built before option selection happens.
    option_instrument_token: Optional[str] = None


class SetupContext(BaseModel):
    """Per-instrument live state — exactly one active (non-terminal)
    setup per instrument at a time, which is what makes duplicate-order
    protection (spec §42) structural rather than a separate check.
    """
    instrument: str
    state: SetupState = SetupState.NO_SETUP
    setup_id: Optional[str] = None
    direction: Optional[SetupDirection] = None
    location_price: Optional[float] = None
    location_reason: Optional[str] = None
    absorption_strength: float = 0.0
    invalidation_price: Optional[float] = None
    created_at: Optional[datetime] = None
    state_entered_at: Optional[datetime] = None
    signal_ready_at: Optional[datetime] = None
    trade_intent: Optional[TradeIntent] = None
