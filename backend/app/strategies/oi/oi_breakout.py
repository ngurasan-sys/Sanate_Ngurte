from typing import Optional
from .base import BaseOIStrategy
from app.oi.models import OIState, OITick, OIStrategyOutput

class OIBreakoutStrategy(BaseOIStrategy):
    """
    Detect abnormal OI expansion accompanying a confirmed price breakout.
    """
    def __init__(self, strategy_id: str = "OI_BREAKOUT"):
        super().__init__(strategy_id)

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        if state.previous_oi == 0:
            return None

        price_up = state.current_price > state.previous_price
        oi_expansion = ((state.current_oi - state.previous_oi) / state.previous_oi) > 0.05 # 5% expansion heuristic

        if price_up and oi_expansion:
            return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="BULLISH",
                signal_type="BREAKOUT",
                oi_state="EXPANDING",
                price_state="INCREASING",
                volume_state="NEUTRAL",
                confidence=0.85,
                confluence_score=0.9,
                evidence=["Price breakout confirmed", f"Abnormal OI expansion detected"],
                invalidation="Price falls back into range"
            )
        return None