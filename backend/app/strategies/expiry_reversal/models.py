from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ExpiryReversalConfig(BaseModel):
    """Configurable thresholds for the Expiry Day Reversal strategy.

    Defaults are reasonable starting points, not the specific numbers from
    any one historical occurrence — tune these against real market data
    before trading live.
    """

    # A. Weak move detection
    weak_candle_body_atr_ratio: float = 0.3  # body/ATR below this => "small, low-momentum" candle
    weak_move_lots: int = 1  # reduced sizing for a weak up-move on expiry day
    normal_lots: int = 2

    # B. OI shift trigger (3-minute window)
    oi_shift_window_minutes: int = 3
    call_oi_increase_threshold: float = 1_000_000.0  # absolute increase in call OI over the window
    put_oi_decrease_threshold: float = 1_000_000.0   # absolute decrease in put OI over the window
    structural_break_min_candles: int = 2  # consecutive large-body candles breaking day low/high

    # C. Laddered execution
    tier_1_lots: int = 2
    tier_2_lots: int = 2
    tier_3_lots: int = 4
    tier_2_offset_points: float = 10.0   # tier 2 entry offset above/below tier 1
    tier_3_offset_points: float = 25.0   # tier 3 entry offset (near prior support/resistance)
    stop_loss_buffer_points: float = 5.0  # SL placed just beyond the breakout candle

    # D. Profit protection
    partial_exit_pct: float = 50.0  # fraction of position booked once price moves favorably

    # E. Time & distance filter
    # Resolved automatically at runtime via expiry_calendar.py (Upstox's
    # real Instrument Search API, expiry=current_week) whenever a saved
    # OAuth token is available — see engine.py's _refresh_expiry_flag().
    # This default only applies before that first successful resolution,
    # or if no token is configured (mock mode): stays False rather than
    # guessing from a hardcoded weekly-expiry-day assumption, which has
    # changed across exchanges/years.
    is_expiry_day: bool = False
    expiry_reference_symbol: str = "NIFTY"
    late_session_start: str = "14:00"  # "around 2:00 PM" caution window, HH:MM
    atr_exhaustion_ratio: float = 0.95  # intraday range / daily ATR >= this => exhausted
    supertrend_period: int = 10
    supertrend_multiplier: float = 3.0


class ExpiryReversalSignal(BaseModel):
    strategy_id: str = "expiry_reversal"
    instrument: str
    action: str  # "ENTER_TIER_1" | "ENTER_TIER_2" | "ENTER_TIER_3" | "CANCEL_PENDING_TIERS" |
                 # "EXIT_PARTIAL" | "TRAIL_SL" | "EXIT_ALL" | "SKIP_LATE_SESSION"
    direction: Optional[str] = None  # "BEARISH" | "BULLISH"
    lots: int = 0
    stop_loss: Optional[float] = None
    reason: str
    timestamp: datetime
