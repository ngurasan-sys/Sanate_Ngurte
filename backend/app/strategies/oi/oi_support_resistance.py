from typing import Optional
from .base import BaseOIStrategy
from backend.app.oi.models import OIState, OITick, OIStrategyOutput

class OISupportResistanceStrategy(BaseOIStrategy):
    """
    Identify strikes with significant OI concentration and determine whether
    they behave as potential support/resistance.
    """
    def __init__(self, strategy_id: str = "OI_SUPPORT_RESISTANCE"):
        super().__init__(strategy_id)

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        # Requires analysis of option chain context (strike vs spot)
        # Using simplified heuristic: high PE OI near price = Support, High CE OI = Resistance

        if state.ce_oi > state.pe_oi * 1.5 and state.strike and state.current_price > 0:
            return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="BEARISH",
                signal_type="RESISTANCE",
                oi_state="HIGH_CALL_OI",
                price_state="NEAR_RESISTANCE",
                volume_state="NEUTRAL",
                confidence=0.75,
                confluence_score=0.8,
                evidence=["High Call OI concentration", "Price approaching level"],
                invalidation="Price breaks and holds above strike"
            )
        elif state.pe_oi > state.ce_oi * 1.5 and state.strike and state.current_price > 0:
            return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="BULLISH",
                signal_type="SUPPORT",
                oi_state="HIGH_PUT_OI",
                price_state="NEAR_SUPPORT",
                volume_state="NEUTRAL",
                confidence=0.75,
                confluence_score=0.8,
                evidence=["High Put OI concentration", "Price approaching level"],
                invalidation="Price breaks and holds below strike"
            )
        return None