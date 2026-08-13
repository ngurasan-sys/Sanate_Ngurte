from typing import Dict, Optional
from datetime import datetime
from .models import OITick, OIState
from .analysis import calculate_pcr

class OIEngine:
    """Manages incremental OI state for all instruments/strikes"""

    def __init__(self):
        # instrument_id (e.g., NIFTY_23NOV23_19000_CE) -> OIState
        self.states: Dict[str, OIState] = {}

    def _generate_state_key(self, tick: OITick) -> str:
        key = tick.instrument
        if tick.expiry:
            key += f"_{tick.expiry}"
        if tick.strike:
            key += f"_{tick.strike}"
        return key

    def process_tick(self, tick: OITick) -> Optional[OIState]:
        """Process incoming tick and update state incrementally"""
        key = self._generate_state_key(tick)

        # Don't update if we have no meaningful data to update
        if tick.price is None and tick.oi is None:
            return self.states.get(key)

        if key not in self.states:
            # Initialize new state
            self.states[key] = OIState(
                instrument=tick.instrument,
                expiry=tick.expiry,
                strike=tick.strike,
                last_update=tick.timestamp,
                current_oi=tick.oi or 0,
                current_price=tick.price or 0.0,
                current_volume=tick.volume or 0,
                vwap=tick.vwap or 0.0,
                ce_oi=tick.ce_oi or 0,
                pe_oi=tick.pe_oi or 0,
                pcr=calculate_pcr(tick.pe_oi or 0, tick.ce_oi or 0)
            )
            return self.states[key]

        state = self.states[key]

        # Update last tick info before mutating
        if tick.oi is not None:
            state.previous_oi = state.current_oi
            state.current_oi = tick.oi

            # Update rolling changes (keep last 10 for analysis)
            oi_change = state.current_oi - state.previous_oi
            if oi_change != 0:
                state.rolling_oi_changes.append(oi_change)
                if len(state.rolling_oi_changes) > 10:
                    state.rolling_oi_changes.pop(0)

        if tick.price is not None:
            state.previous_price = state.current_price
            state.current_price = tick.price

        if tick.volume is not None:
            state.previous_volume = state.current_volume
            state.current_volume = tick.volume

        if tick.vwap is not None:
            state.vwap = tick.vwap

        if tick.ce_oi is not None:
            state.ce_oi = tick.ce_oi
        if tick.pe_oi is not None:
            state.pe_oi = tick.pe_oi

        state.pcr = calculate_pcr(state.pe_oi, state.ce_oi)
        state.last_update = tick.timestamp

        return state

    def get_state(self, instrument: str, expiry: Optional[str] = None, strike: Optional[float] = None) -> Optional[OIState]:
        key = instrument
        if expiry:
            key += f"_{expiry}"
        if strike:
            key += f"_{strike}"
        return self.states.get(key)