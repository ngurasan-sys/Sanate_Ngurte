from typing import Optional
from .base import BaseOIStrategy
from app.oi.models import OIState, OITick, OIStrategyOutput

class TrendingOIStrategy(BaseOIStrategy):
    """
    Identify sustained directional OI changes across consecutive observations.
    """
    def __init__(self, strategy_id: str = "TRENDING_OI"):
        super().__init__(strategy_id)

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        if len(state.rolling_oi_changes) < 3:
            return None

        recent_changes = state.rolling_oi_changes[-3:]

        if all(c > 0 for c in recent_changes):
             return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="TRENDING",
                signal_type="MOMENTUM",
                oi_state="CONSISTENT_INCREASE",
                price_state="NEUTRAL",
                volume_state="NEUTRAL",
                confidence=0.8,
                confluence_score=0.6,
                evidence=["Sustained OI increases across consecutive ticks"],
                invalidation="OI change turns negative"
            )
        elif all(c < 0 for c in recent_changes):
             return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="TRENDING",
                signal_type="MOMENTUM",
                oi_state="CONSISTENT_DECREASE",
                price_state="NEUTRAL",
                volume_state="NEUTRAL",
                confidence=0.8,
                confluence_score=0.6,
                evidence=["Sustained OI decreases across consecutive ticks"],
                invalidation="OI change turns positive"
            )
        return None