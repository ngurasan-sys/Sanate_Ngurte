from typing import Optional
from .base import BaseOIStrategy
from app.oi.models import OIState, OITick, OIStrategyOutput

class OIConfluenceStrategy(BaseOIStrategy):
    """
    Combined OI and Level strategies (e.g. Resistance + Call OI concentration)
    """
    def __init__(self, strategy_id: str = "OI_CONFLUENCE"):
        super().__init__(strategy_id)

    def analyze(self, tick: OITick, state: OIState) -> Optional[OIStrategyOutput]:
        # For a full implementation this requires levels data and vwap
        # We simulate the VWAP rejection/reclaim here as requested

        if state.previous_price == 0 or state.vwap == 0:
            return None

        vwap_reclaim = state.previous_price < state.vwap and state.current_price > state.vwap
        vwap_rejection = state.previous_price > state.vwap and state.current_price < state.vwap

        high_put_oi = state.pe_oi > state.ce_oi * 1.5
        high_call_oi = state.ce_oi > state.pe_oi * 1.5

        if vwap_reclaim and high_put_oi:
             return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="BULLISH",
                signal_type="CONFLUENCE",
                oi_state="SUPPORTIVE",
                price_state="RECLAIM",
                vwap_state="RECLAIMED",
                volume_state="NEUTRAL",
                confidence=0.9,
                confluence_score=0.95,
                evidence=["VWAP Reclaimed", "High Put OI (Support)"],
                invalidation="Price drops below VWAP"
            )

        if vwap_rejection and high_call_oi:
             return OIStrategyOutput(
                strategy_id=self.strategy_id,
                instrument=state.instrument,
                expiry=state.expiry,
                strike=state.strike,
                timestamp=state.last_update,
                direction="BEARISH",
                signal_type="CONFLUENCE",
                oi_state="RESISTANT",
                price_state="REJECTED",
                vwap_state="REJECTED",
                volume_state="NEUTRAL",
                confidence=0.9,
                confluence_score=0.95,
                evidence=["VWAP Rejected", "High Call OI (Resistance)"],
                invalidation="Price reclaims VWAP"
            )

        return None