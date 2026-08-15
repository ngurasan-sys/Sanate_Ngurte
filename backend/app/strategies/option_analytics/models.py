from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class OptionAnalyticsConfig(BaseModel):
    """Thresholds for the IV-regime and PCR-extreme strategies.

    Defaults are reasonable starting points, not calibrated values —
    tune against real observed data for your instrument before trading.
    """

    underlying_key: str = "NSE_INDEX|Nifty 50"
    poll_interval_seconds: int = 5

    # --- IV regime ---
    # An IV reading of exactly 0.0 comes back from Upstox for illiquid /
    # no-solution strikes. It is NOT a real "zero volatility" reading and
    # must never be averaged in — see is_valid_iv().
    iv_history_window: int = 60  # samples retained for the intraday baseline
    iv_crush_drop_pct: float = 8.0    # ATM IV falling this % from baseline => crush
    iv_expansion_rise_pct: float = 8.0  # ATM IV rising this % from baseline => expansion
    iv_skew_threshold: float = 3.0   # abs(put IV - call IV) in vol points to flag skew
    skew_strike_offset: int = 3      # how many strikes OTM each side to measure skew

    # --- PCR extremes ---
    pcr_history_window: int = 60
    pcr_high_extreme: float = 1.5   # >= this = excessive put writing (contrarian bullish)
    pcr_low_extreme: float = 0.6    # <= this = excessive call writing (contrarian bearish)
    pcr_reversal_delta: float = 0.15  # move back from the extreme needed to confirm a turn


class IvRegimeState(BaseModel):
    sufficient_data: bool
    reason: Optional[str] = None
    atm_iv: Optional[float] = None
    baseline_iv: Optional[float] = None
    iv_change_pct: Optional[float] = None
    regime: str = "UNKNOWN"  # IV_CRUSH | IV_EXPANSION | IV_STABLE | UNKNOWN
    skew: Optional[float] = None  # put IV - call IV, in vol points
    skew_bias: str = "NEUTRAL"    # PUT_SKEW | CALL_SKEW | NEUTRAL
    signal: str = "NONE"          # SELL_PREMIUM | BUY_PREMIUM | NONE
    reasoning: Optional[str] = None


class PcrReversalState(BaseModel):
    sufficient_data: bool
    reason: Optional[str] = None
    pcr: Optional[float] = None
    pcr_peak: Optional[float] = None
    pcr_trough: Optional[float] = None
    zone: str = "NEUTRAL"  # HIGH_EXTREME | LOW_EXTREME | NEUTRAL
    signal: str = "NONE"   # CONTRARIAN_BULLISH | CONTRARIAN_BEARISH | NONE
    reasoning: Optional[str] = None


class OptionAnalyticsSnapshot(BaseModel):
    timestamp: datetime
    underlying_key: str
    spot_price: Optional[float] = None
    atm_strike: Optional[float] = None
    iv_regime: IvRegimeState
    pcr_reversal: PcrReversalState
