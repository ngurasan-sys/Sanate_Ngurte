from fastapi import APIRouter, HTTPException
from typing import Optional, Dict, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

# Will be injected at startup
_gap_opening_engine = None
_tick_processor_market_state = None

def set_gap_opening_engine(engine):
    """Inject the gap_opening_engine instance."""
    global _gap_opening_engine
    _gap_opening_engine = engine

def set_market_state(state_dict):
    """Inject current market state (aggregated from tick processor)."""
    global _tick_processor_market_state
    _tick_processor_market_state = state_dict

@router.get("/api/v1/market/indices")
def get_market_indices():
    """
    Fetch current market indices (NIFTY, SENSEX, BANKNIFTY).
    Returns spot price, change %, VWAP, support, resistance, IV, expected move.
    """
    if not _gap_opening_engine:
        return {
            "status": "NO DATA",
            "indices": {}
        }

    engine = _gap_opening_engine
    indices = {}

    for instrument in ["NIFTY", "SENSEX", "BANKNIFTY"]:
        # Get last price from context
        last_price = engine.context.get(instrument, {}).get("last_price")
        previous_close = engine.previous_close.get(instrument)
        day_high = engine.day_high.get(instrument)
        day_low = engine.day_low.get(instrument)
        vwap = engine.vwap.get(instrument)
        oi_regime = engine.oi_regime.get(instrument, "UNKNOWN")
        diff_oi_pct = engine.diff_oi_pct.get(instrument)

        if not last_price:
            continue

        change = last_price - previous_close if previous_close else 0.0
        change_pct = (change / previous_close * 100) if previous_close else 0.0

        # IV and expected_move are not in gap_opening_engine yet
        # Return placeholder until greeks_engine provides them
        iv = None
        expected_move = None

        indices[instrument] = {
            "instrument": instrument,
            "spot": round(last_price, 2),
            "change": round(change, 2),
            "changePercent": round(change_pct, 2),
            "dayHigh": round(day_high, 2) if day_high else None,
            "dayLow": round(day_low, 2) if day_low else None,
            "vwap": round(vwap, 2) if vwap else None,
            "support": None,  # Computed by levels engine, not here
            "resistance": None,  # Computed by levels engine, not here
            "iv": iv,
            "expectedMove": expected_move,
            "oiRegime": oi_regime,
            "diffOiPct": diff_oi_pct,
            "lastUpdate": datetime.utcnow().isoformat()
        }

    return {
        "status": "LIVE" if indices else "NO DATA",
        "indices": indices
    }

@router.get("/api/v1/market/indices/{instrument}")
def get_market_index(instrument: str):
    """Fetch a single index by name (NIFTY, SENSEX, BANKNIFTY)."""
    normalized = instrument.upper()

    if not _gap_opening_engine:
        raise HTTPException(status_code=503, detail="Market engine not ready")

    engine = _gap_opening_engine

    if normalized not in engine.context:
        raise HTTPException(status_code=404, detail=f"Index {instrument} not found")

    last_price = engine.context.get(normalized, {}).get("last_price")
    previous_close = engine.previous_close.get(normalized)
    day_high = engine.day_high.get(normalized)
    day_low = engine.day_low.get(normalized)
    vwap = engine.vwap.get(normalized)
    oi_regime = engine.oi_regime.get(normalized, "UNKNOWN")
    diff_oi_pct = engine.diff_oi_pct.get(normalized)

    if not last_price:
        raise HTTPException(status_code=503, detail=f"No live data for {instrument}")

    change = last_price - previous_close if previous_close else 0.0
    change_pct = (change / previous_close * 100) if previous_close else 0.0

    return {
        "instrument": normalized,
        "spot": round(last_price, 2),
        "change": round(change, 2),
        "changePercent": round(change_pct, 2),
        "dayHigh": round(day_high, 2) if day_high else None,
        "dayLow": round(day_low, 2) if day_low else None,
        "vwap": round(vwap, 2) if vwap else None,
        "support": None,
        "resistance": None,
        "iv": None,
        "expectedMove": None,
        "oiRegime": oi_regime,
        "diffOiPct": diff_oi_pct,
        "lastUpdate": datetime.utcnow().isoformat()
    }
