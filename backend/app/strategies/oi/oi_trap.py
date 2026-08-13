from typing import Optional
from .base import BaseOIStrategy
from backend.app.oi.models import OIState, OITick, OIStrategyOutput

class OITrapStrategy(BaseOIStrategy):
    """
    Detect situations where OI positioning appears crowded but price action
    fails to confirm the expected direction.
    """
    def __init__(self, strategy_id: str = "OI_TRAP"):
        super().__init__(strategy_id)

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        if state.previous_oi == 0 or state.previous_price == 0:
            return None

        # Example Trap: Huge long build-up previously, but now price is violently dropping
        if state.current_oi > state.previous_oi * 1.05 and state.current_price < state.previous_price * 0.99:
             return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="BEARISH", # Bulls are trapped, expecting downward cascade
                signal_type="TRAP",
                oi_state="CROWDED_LONGS",
                price_state="REJECTED",
                volume_state="NEUTRAL",
                confidence=0.8,
                confluence_score=0.7,
                evidence=["OI increased significantly but price fell (Bull Trap)"],
                invalidation="Price reclaims VWAP rapidly"
            )
        return None