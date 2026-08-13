from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class OITick(BaseModel):
    """Incoming OI Data tick"""
    instrument: str
    timestamp: datetime

    # Core identifiers
    expiry: Optional[str] = None
    strike: Optional[float] = None

    # OI data
    oi: Optional[int] = None
    previous_oi: Optional[int] = None
    oi_change: Optional[int] = None
    oi_change_pct: Optional[float] = None

    # Price & Volume
    price: Optional[float] = None
    price_change: Optional[float] = None
    volume: Optional[int] = None
    volume_change: Optional[int] = None
    vwap: Optional[float] = None

    # Option specific
    iv: Optional[float] = None
    ce_oi: Optional[int] = None
    pe_oi: Optional[int] = None
    ce_oi_change: Optional[int] = None
    pe_oi_change: Optional[int] = None
    pcr: Optional[float] = None

    # Future specific
    futures_oi: Optional[int] = None
    futures_price: Optional[float] = None
    spot_price: Optional[float] = None
    basis: Optional[float] = None
    basis_change: Optional[float] = None


class OIState(BaseModel):
    """Incremental state for OI calculations"""
    instrument: str
    expiry: Optional[str] = None
    strike: Optional[float] = None
    last_update: datetime

    current_oi: int = 0
    previous_oi: int = 0
    current_price: float = 0.0
    previous_price: float = 0.0
    current_volume: int = 0
    previous_volume: int = 0
    vwap: float = 0.0

    ce_oi: int = 0
    pe_oi: int = 0
    pcr: float = 0.0

    # Used for tracking buildups over time
    rolling_oi_changes: List[int] = Field(default_factory=list)


class OIStrategyOutput(BaseModel):
    """Standardized output for all OI Strategies"""
    strategy_id: str
    instrument: str
    expiry: Optional[str] = None
    strike: Optional[float] = None
    timestamp: datetime

    direction: str
    signal_type: str

    oi_state: str
    price_state: str
    volume_state: str
    vwap_state: Optional[str] = None
    level_state: Optional[str] = None
    liquidity_state: Optional[str] = None

    confidence: float
    confluence_score: float

    evidence: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    invalidation: str
    target_levels: List[float] = Field(default_factory=list)
