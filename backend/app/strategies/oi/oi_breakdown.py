from typing import Optional
from .base import BaseOIStrategy
from backend.app.oi.models import OIState, OITick, OIStrategyOutput

class OIBreakdownStrategy(BaseOIStrategy):
    """
    Detect abnormal OI expansion accompanying a confirmed price breakdown.
    """
    def __init__(self, strategy_id: str = "OI_BREAKDOWN"):
        super().__init__(strategy_id)

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        if state.previous_oi == 0:
            return None

        price_down = state.current_price < state.previous_price
        oi_expansion = ((state.current_oi - state.previous_oi) / state.previous_oi) > 0.05 # 5% expansion heuristic

        if price_down and oi_expansion:
            return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="BEARISH",
                signal_type="BREAKDOWN",
                oi_state="EXPANDING",
                price_state="DECREASING",
                volume_state="NEUTRAL",
                confidence=0.85,
                confluence_score=0.9,
                evidence=["Price breakdown confirmed", f"Abnormal OI expansion detected"],
                invalidation="Price reclaims breakdown level"
            )
        return None