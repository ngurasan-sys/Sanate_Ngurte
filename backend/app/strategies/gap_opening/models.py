from pydantic import BaseModel
from typing import Literal, Optional, List
from datetime import datetime

class StrategyConfig(BaseModel):
    opening_time: str = "09:15"
    entry_start_time: str = "09:45"
    oi_bullish_threshold: float = 40.0
    oi_bearish_threshold: float = -40.0
    supertrend_period: int = 10
    supertrend_multiplier: int = 3
    atr_period: int = 14
    atr_exhaustion_ratio: float = 0.95
    vix_override_threshold: float = 15.0
    round_number_distance: int = 35
    bullish_vwap_buffer: int = 10
    bearish_stop_buffer: int = 12
    tier_1_lots: int = 2
    tier_2_lots: int = 2
    low_momentum_lots: int = 2
    partial_profit_points: int = 25
    partial_profit_percent: int = 50
    expansion_candle_points: int = 30
    trailing_buffer: int = 10
    max_position_lots: int = 10
    tier_2_buffer: int = 10


class SelectedOption(BaseModel):
    instrument_key: str
    strike_price: int
    option_type: Literal["CE", "PE"]
    expiry: str


class PositionState(BaseModel):
    in_position: bool = False
    direction: Optional[Literal["BULLISH", "BEARISH"]] = None
    underlying: Optional[str] = None
    selected_strike: Optional[int] = None
    instrument_key: Optional[str] = None
    option_type: Optional[str] = None
    expiry: Optional[str] = None
    entry_price: float = 0.0
    average_entry_price: float = 0.0
    lots_held: int = 0
    initial_lots: int = 0
    tier_2_filled: bool = False
    partial_booked: bool = False
    event_pyramid_used: bool = False
    current_sl: float = 0.0
    highest_favorable_price: float = 0.0
    lowest_favorable_price: float = 0.0
    position_state: str = "WAITING_FOR_DISCOVERY"
    entry_timestamp: Optional[datetime] = None


class StrategySignal(BaseModel):
    signal_id: str
    strategy_id: str
    strategy_name: str
    symbol: str
    underlying: str
    action: Literal[
        "BUY_CE",
        "BUY_PE",
        "ADD_TIER_2",
        "EVENT_PYRAMID",
        "EXIT_PARTIAL",
        "EXIT_ALL",
        "TRAIL_SL"
    ]
    strike_price: int
    instrument_key: str
    option_type: str
    expiry: str
    underlying_price: float
    option_price: float
    stop_loss: float
    lots: int
    regime: str
    mode: str
    diff_oi_pct: float
    net_pcr: float
    vwap: float
    supertrend: float
    daily_atr: float
    atr_exhausted: bool
    vix_1h_change_pct: float
    vix_override: bool
    reason: str
    timestamp: datetime
