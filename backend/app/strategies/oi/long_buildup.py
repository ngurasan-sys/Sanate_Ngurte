from typing import Optional
from .base import BaseOIStrategy
from backend.app.oi.models import OIState, OITick, OIStrategyOutput

class LongBuildupStrategy(BaseOIStrategy):
    """
    Detects Long Build-up:
    Price up + OI up + Volume confirmation + VWAP confirmation
    """
    def __init__(self, strategy_id: str = "LONG_BUILDUP"):
        super().__init__(strategy_id)

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        if state.previous_price == 0 or state.previous_oi == 0:
            return None

        price_up = state.current_price > state.previous_price
        oi_up = state.current_oi > state.previous_oi

        # Confirmation heuristics
        vol_conf = state.current_volume > state.previous_volume if state.previous_volume > 0 else True
        vwap_conf = state.current_price > state.vwap if state.vwap > 0 else True

        if price_up and oi_up and vol_conf and vwap_conf:
            return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="BULLISH",
                signal_type="ENTRY",
                oi_state="INCREASING",
                price_state="INCREASING",
                volume_state="CONFIRMED" if vol_conf else "NEUTRAL",
                vwap_state="ABOVE" if vwap_conf else "BELOW",
                confidence=0.8,
                confluence_score=0.8,
                evidence=["Price increased", "OI increased", "Volume confirmed", "Above VWAP"],
                invalidation="Price drops below VWAP or OI starts unwinding"
            )
        return None