from typing import Optional
from .base import BaseOIStrategy
from backend.app.oi.models import OIState, OITick, OIStrategyOutput
from backend.app.oi.analysis import classify_buildup

class OIBuildupStrategy(BaseOIStrategy):
    """
    General Buildup wrapper combining long/short buildup/unwinding signals based on analysis.
    """
    def __init__(self, strategy_id: str = "OI_BUILDUP"):
        super().__init__(strategy_id)

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        if state.previous_price == 0 or state.previous_oi == 0:
            return None

        classification = classify_buildup(state.current_price, state.previous_price, state.current_oi, state.previous_oi)

        if classification == "NEUTRAL":
            return None

        direction = "BULLISH" if classification in ["LONG_BUILDUP", "SHORT_COVERING"] else "BEARISH"

        return OIStrategyOutput(
            strategy_id=self.strategy_id,
            instrument=state.instrument,
            expiry=state.expiry,
            strike=state.strike,
            timestamp=state.last_update,
            direction=direction,
            signal_type="BUILDUP_STATE",
            oi_state=classification,
            price_state="TRENDING",
            volume_state="NEUTRAL",
            confidence=0.6,
            confluence_score=0.5,
            evidence=[f"Buildup state: {classification}"],
            invalidation="State changes"
        )