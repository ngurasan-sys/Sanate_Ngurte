from fastapi import APIRouter, HTTPException
from typing import Dict, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

# Will be injected at startup
_risk_engine = None

def set_risk_engine(engine):
    """Inject the risk_engine instance."""
    global _risk_engine
    _risk_engine = engine

@router.get("/api/v1/risk/summary")
def get_risk_summary():
    """
    Fetch current risk summary.
    Returns: { availableCapital, availableMargin, marginUsed, dailyPnl, dailyLossLimit, exposure, riskStatus }
    """
    if not _risk_engine:
        return {
            "status": "NO DATA",
            "summary": {
                "availableCapital": None,
                "availableMargin": None,
                "marginUsed": None,
                "dailyPnl": None,
                "dailyLossLimit": None,
                "exposure": None,
                "riskStatus": "UNKNOWN",
                "lastUpdate": datetime.utcnow().isoformat()
            }
        }

    engine = _risk_engine

    # Extract fields from risk_engine state
    available_capital = getattr(engine, "available_capital", None)
    available_margin = getattr(engine, "available_margin", None)
    margin_used = getattr(engine, "margin_used", None)
    daily_pnl = getattr(engine, "daily_pnl", None)
    daily_loss_limit = getattr(engine, "daily_loss_limit", None)
    exposure = getattr(engine, "exposure", None)
    risk_status = getattr(engine, "risk_status", "UNKNOWN")

    # If daily_pnl available, compute margin_used from available_capital - available_margin
    if available_capital and available_margin:
        margin_used = available_capital - available_margin

    return {
        "status": "LIVE" if (available_capital or available_margin) else "NO DATA",
        "summary": {
            "availableCapital": available_capital,
            "availableMargin": available_margin,
            "marginUsed": margin_used,
            "dailyPnl": daily_pnl,
            "dailyLossLimit": daily_loss_limit,
            "exposure": exposure,
            "riskStatus": risk_status,
            "lastUpdate": datetime.utcnow().isoformat()
        }
    }

@router.post("/api/v1/risk/acknowledge")
def acknowledge_risk():
    """Acknowledge a risk alert (future: gate execution until acknowledged)."""
    if not _risk_engine:
        raise HTTPException(status_code=503, detail="Risk engine not ready")

    # Mark as acknowledged in engine
    if hasattr(_risk_engine, "acknowledged"):
        _risk_engine.acknowledged = True
        logger.info("Risk alert acknowledged")

    return {"status": "acknowledged"}
