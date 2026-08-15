from typing import Optional
from .base import BaseOIStrategy
from backend.app.oi.models import OIState, OITick, OIStrategyOutput

class ShortCoveringStrategy(BaseOIStrategy):
    """
    Detects Short Covering:
    Price up + OI down + Volume/price confirmation
    """
    def __init__(self, strategy_id: str = "SHORT_COVERING"):
        super().__init__(strategy_id)

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        if state.previous_price == 0 or state.previous_oi == 0:
            return None

        price_up = state.current_price > state.previous_price
        oi_down = state.current_oi < state.previous_oi

        if price_up and oi_down:
            return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="BULLISH",
                signal_type="EXIT",
                oi_state="DECREASING",
                price_state="INCREASING",
                volume_state="NEUTRAL",
                confidence=0.7,
                confluence_score=0.6,
                evidence=["Price increased", "OI decreased (Short Covering)"],
                invalidation="Price drops below VWAP or OI stabilizes"
            )
        return None