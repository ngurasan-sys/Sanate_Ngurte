from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


class CASDislocationConfig(BaseModel):
    """The dedicated config for this engine — deliberately separate from
    AlgoTradingConfig and manual_trading: this strategy is independent,
    with its own lot size, thresholds, and arm switch.
    """

    underlying: str = "NIFTY"          # NIFTY | BANKNIFTY | SENSEX
    enabled: bool = False
    lots: int = 1
    max_hold_seconds: int = 90         # time-based exit, not a fixed clock time — the
                                        # dislocation is short-lived by nature (spec: 60-120s)
    min_score_to_alert: int = 60       # radar/UI highlights a candidate at this score
    min_score_to_execute: int = 85     # engine will only auto-fire at/above this
    auto_execute: bool = False         # extra explicit switch: enabled alone only alerts;
                                        # auto_execute must ALSO be on to place real orders
    updated_at: Optional[datetime] = None


class CASConfigError(Exception):
    """Raised when a configure/enable request is invalid."""


class FreezeSnapshot(BaseModel):
    """Captured once, at the moment continuous trading ends (~15:15:00).
    Everything downstream compares against this fixed reference.
    """

    frozen_spot: float
    frozen_at: datetime
    atm_strike: float
    future_price_at_freeze: float
    baseline_ce_iv: float
    baseline_pe_iv: float
    baseline_volume_rate: float        # avg volume delta per poll during PRE_CAS


class CASReading(BaseModel):
    """One scored snapshot of the dislocation state, published live over
    the websocket for the radar UI.
    """

    timestamp: datetime
    state: Literal["PRE_CAS", "CAS_FREEZE", "DISLOCATION", "VOLATILITY_SHOCK", "SIGNAL", "INACTIVE"]
    frozen_spot: Optional[float] = None
    future_price: Optional[float] = None
    future_displacement: Optional[float] = None
    future_velocity: Optional[float] = None   # points/sec, recent window

    atm_strike: Optional[float] = None
    ce_bid: Optional[float] = None
    ce_ask: Optional[float] = None
    ce_theoretical: Optional[float] = None
    ce_dislocation_pct: Optional[float] = None
    pe_bid: Optional[float] = None
    pe_ask: Optional[float] = None
    pe_theoretical: Optional[float] = None
    pe_dislocation_pct: Optional[float] = None

    iv_shift_ce: Optional[float] = None
    iv_shift_pe: Optional[float] = None
    volume_acceleration: Optional[float] = None

    score: int = 0
    signal: Literal["NONE", "BUY_CE", "BUY_PE"] = "NONE"
    reason: str = ""


class CASPosition(BaseModel):
    position_id: str
    underlying: str
    option_type: Literal["CE", "PE"]
    strike: float
    instrument_token: str
    lots: int
    quantity: int
    entry_price: float
    max_hold_seconds: int
    status: Literal["PENDING", "OPEN", "CLOSED"] = "PENDING"
    created_at: datetime
    opened_at: Optional[datetime] = None  # confirmed-OPEN time — max_hold counts from here, not created_at
    closed_at: Optional[datetime] = None
    exit_reason: Optional[str] = None
    last_ltp: Optional[float] = None
