from typing import Optional
from .base import BaseOIStrategy
from backend.app.oi.models import OIState, OITick, OIStrategyOutput

class OIPriceDivergenceStrategy(BaseOIStrategy):
    """
    Detect divergence between Price and OI.
    (e.g., Price making new highs but OI dropping)
    """
    def __init__(self, strategy_id: str = "OI_PRICE_DIVERGENCE"):
        super().__init__(strategy_id)

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        if state.previous_price == 0 or state.previous_oi == 0:
            return None

        price_up = state.current_price > state.previous_price * 1.01 # 1% increase
        oi_down = state.current_oi < state.previous_oi * 0.99 # 1% decrease

        if price_up and oi_down:
             return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="BEARISH", # Weak rally
                signal_type="DIVERGENCE",
                oi_state="DECREASING",
                price_state="INCREASING",
                volume_state="NEUTRAL",
                confidence=0.7,
                confluence_score=0.6,
                evidence=["Price rallying but OI dropping (Weakness)"],
                invalidation="OI starts increasing with price"
            )

        price_down = state.current_price < state.previous_price * 0.99
        oi_up_divergence = state.current_oi < state.previous_oi * 0.99

        if price_down and oi_up_divergence:
             return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="BULLISH", # Weak selloff
                signal_type="DIVERGENCE",
                oi_state="DECREASING",
                price_state="DECREASING",
                volume_state="NEUTRAL",
                confidence=0.7,
                confluence_score=0.6,
                evidence=["Price dropping but OI dropping (Lack of conviction)"],
                invalidation="OI starts increasing with selloff"
            )
        return None