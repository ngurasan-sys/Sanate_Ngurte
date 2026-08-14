from typing import Optional
from .base import BaseOIStrategy
from app.oi.models import OIState, OITick, OIStrategyOutput

class ShortBuildupStrategy(BaseOIStrategy):
    """
    Detects Short Build-up:
    Price down + OI up + Volume confirmation + VWAP confirmation
    """
    def __init__(self, strategy_id: str = "SHORT_BUILDUP"):
        super().__init__(strategy_id)

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        if state.previous_price == 0 or state.previous_oi == 0:
            return None

        price_down = state.current_price < state.previous_price
        oi_up = state.current_oi > state.previous_oi

        # Confirmation heuristics
        vol_conf = state.current_volume > state.previous_volume if state.previous_volume > 0 else True
        vwap_conf = state.current_price < state.vwap if state.vwap > 0 else True

        if price_down and oi_up and vol_conf and vwap_conf:
            return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="BEARISH",
                signal_type="ENTRY",
                oi_state="INCREASING",
                price_state="DECREASING",
                volume_state="CONFIRMED" if vol_conf else "NEUTRAL",
                vwap_state="BELOW" if vwap_conf else "ABOVE",
                confidence=0.8,
                confluence_score=0.8,
                evidence=["Price decreased", "OI increased", "Volume confirmed", "Below VWAP"],
                invalidation="Price rises above VWAP or OI starts unwinding"
            )
        return None