from typing import Optional
from .base import BaseOIStrategy
from backend.app.oi.models import OIState, OITick, OIStrategyOutput
from backend.app.oi.analysis import classify_buildup

class OIReversalStrategy(BaseOIStrategy):
    """
    Detect significant changes from buildup to unwinding.
    """
    def __init__(self, strategy_id: str = "OI_REVERSAL"):
        super().__init__(strategy_id)
        # Tracking prev state to see transition would be ideal,
        # Here we look for sharp OI drops after price rallies

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        if state.previous_oi == 0:
            return None

        # Simplified: if OI was very high and just dropped significantly
        oi_drop = ((state.previous_oi - state.current_oi) / state.previous_oi) > 0.05

        if oi_drop:
             return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="UNKNOWN", # Depends on context (Long unwinding vs Short covering)
                signal_type="REVERSAL",
                oi_state="UNWINDING_RAPIDLY",
                price_state="NEUTRAL",
                volume_state="NEUTRAL",
                confidence=0.75,
                confluence_score=0.7,
                evidence=["Significant sudden drop in OI (Reversal)"],
                invalidation="OI stabilizes"
            )
        return None