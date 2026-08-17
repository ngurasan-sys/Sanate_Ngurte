from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

# Will be injected at startup
_option_analytics_engine = None

def set_option_analytics_engine(engine):
    """Inject the option_analytics_engine instance."""
    global _option_analytics_engine
    _option_analytics_engine = engine

@router.get("/api/v1/option-chain")
def list_option_chains(instrument: str = Query("NIFTY")):
    """
    Fetch all available option chains for an instrument.
    Returns list of expirations available.
    """
    return {
        "instrument": instrument.upper(),
        "expirations": [],
        "timestamp": datetime.utcnow().isoformat(),
        "status": "NO DATA - option chain endpoint not yet wired to live data source"
    }

@router.get("/api/v1/option-chain/{instrument}")
def get_option_chain(instrument: str, expiry: Optional[str] = Query(None)):
    """
    Fetch option chain for an instrument and optional expiry.
    Returns array of strikes with CE/PE data: { strike, ce: { ltp, bid, ask, oi, volume, iv, greeks }, pe: { ... } }

    NOTE: This endpoint is a placeholder. Currently, option chain data is not
    aggregated in the backend — it flows directly from broker APIs (Upstox/Dhan)
    to individual strategy engines. To wire this endpoint to live data:

    1. Create an OptionChainEngine that maintains a per-instrument, per-expiry
       state of all strikes (similar to LevelEngine for support/resistance).
    2. Have the broker data providers (upstox_provider, dhan_provider) publish
       option-chain ticks to the event bus (e.g., "OPTION_TICK" events).
    3. Subscribe this endpoint's engine to those events and maintain state.
    4. Optionally: Add a /ws/option_chain websocket channel for real-time updates.

    Until then, frontend will receive "NO DATA" and should either:
    - Continue using mock data (acceptable for non-critical displays)
    - Poll an external option chain API (e.g., Upstox's search/instruments endpoints)
    - Wait for backend implementation
    """
    if not _option_analytics_engine:
        return {
            "instrument": instrument.upper(),
            "expiry": expiry or "CURRENT",
            "strikes": [],
            "timestamp": datetime.utcnow().isoformat(),
            "status": "NO DATA - option analytics engine not ready"
        }

    return {
        "instrument": instrument.upper(),
        "expiry": expiry or "CURRENT",
        "strikes": [],
        "timestamp": datetime.utcnow().isoformat(),
        "status": "NO DATA - option chain data not aggregated in backend yet"
    }

@router.get("/api/v1/option-chain/{instrument}/{expiry}/strike/{strike}")
def get_option_strike(instrument: str, expiry: str, strike: float):
    """
    Fetch a single strike's CE/PE data.
    Returns: { strike, ce: { ltp, bid, ask, oi, volume, iv, delta, gamma, theta, vega }, pe: { ... } }
    """
    return {
        "instrument": instrument.upper(),
        "expiry": expiry,
        "strike": strike,
        "ce": {},
        "pe": {},
        "timestamp": datetime.utcnow().isoformat(),
        "status": "NO DATA"
    }
