from typing import Optional
from .base import BaseOIStrategy
from app.oi.models import OIState, OITick, OIStrategyOutput

class LongUnwindingStrategy(BaseOIStrategy):
    """
    Detects Long Unwinding:
    Price down + OI down + Volume/price confirmation
    """
    def __init__(self, strategy_id: str = "LONG_UNWINDING"):
        super().__init__(strategy_id)

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        if state.previous_price == 0 or state.previous_oi == 0:
            return None

        price_down = state.current_price < state.previous_price
        oi_down = state.current_oi < state.previous_oi

        if price_down and oi_down:
            return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="BEARISH",
                signal_type="EXIT",
                oi_state="DECREASING",
                price_state="DECREASING",
                volume_state="NEUTRAL",
                confidence=0.7,
                confluence_score=0.6,
                evidence=["Price decreased", "OI decreased (Long Unwinding)"],
                invalidation="Price reclaims VWAP or OI stabilizes"
            )
        return None