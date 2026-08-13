from typing import Optional
import numpy as np
from .base import BaseOIStrategy
from backend.app.oi.models import OIState, OITick, OIStrategyOutput

class UnusualOIStrategy(BaseOIStrategy):
    """
    Detect statistically abnormal OI changes relative to historical/intraday baselines.
    """
    def __init__(self, strategy_id: str = "UNUSUAL_OI"):
        super().__init__(strategy_id)

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        if len(state.rolling_oi_changes) < 5 or state.previous_oi == 0:
            return None

        current_change = state.current_oi - state.previous_oi
        if current_change == 0:
            return None

        mean_change = np.mean(np.abs(state.rolling_oi_changes))
        std_change = np.std(np.abs(state.rolling_oi_changes))

        # Avoid division by zero and zero std dev
        if std_change == 0:
            return None

        z_score = (abs(current_change) - mean_change) / std_change

        if z_score > 2.5: # Statistically significant spike
            direction = "UNKNOWN"
            if state.current_price > state.previous_price and current_change > 0:
                direction = "BULLISH"
            elif state.current_price < state.previous_price and current_change > 0:
                direction = "BEARISH"

            return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction=direction,
                signal_type="ALERT",
                oi_state="ANOMALY",
                price_state="NEUTRAL",
                volume_state="NEUTRAL",
                confidence=0.7,
                confluence_score=0.5,
                evidence=[f"Z-Score {z_score:.2f} spike in OI change"],
                invalidation="OI normalizes or price fails to follow"
            )
        return None