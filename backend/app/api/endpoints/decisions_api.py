from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

# Will be injected at startup
_decision_engine = None

def set_decision_engine(engine):
    """Inject the decision_engine instance."""
    global _decision_engine
    _decision_engine = engine

@router.get("/api/v1/decisions")
def list_decisions(limit: int = Query(50, ge=1, le=200)):
    """
    Fetch decision history and current decisions.
    Returns: [ { id, timestamp, strategy, instrument, action, confidence, status, setupId, riskAssessment } ]
    """
    if not _decision_engine:
        return {
            "decisions": [],
            "count": 0,
            "timestamp": datetime.utcnow().isoformat()
        }

    engine = _decision_engine

    # Get decisions from engine history (if maintained)
    decisions_list = []
    if hasattr(engine, "decisions"):
        decisions_list = list(engine.decisions.values())
    elif hasattr(engine, "decision_history"):
        decisions_list = engine.decision_history[-limit:]

    # Convert to API format
    decisions = []
    for dec in decisions_list:
        if isinstance(dec, dict):
            decisions.append({
                "id": dec.get("decision_id", "UNKNOWN"),
                "timestamp": dec.get("timestamp", datetime.utcnow().isoformat()),
                "strategy": dec.get("strategy"),
                "instrument": dec.get("instrument"),
                "action": dec.get("action"),
                "confidence": dec.get("confidence"),
                "status": dec.get("status", "PENDING"),
                "setupId": dec.get("setup_id"),
                "riskAssessment": dec.get("risk_assessment", {})
            })

    return {
        "decisions": decisions[-limit:],
        "count": len(decisions),
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/api/v1/decisions/{decision_id}")
def get_decision(decision_id: str):
    """Fetch a single decision by ID."""
    if not _decision_engine:
        raise HTTPException(status_code=503, detail="Decision engine not ready")

    engine = _decision_engine

    # Lookup decision
    decision = None
    if hasattr(engine, "decisions"):
        decision = engine.decisions.get(decision_id)
    elif hasattr(engine, "decision_history"):
        decision = next((d for d in engine.decision_history if d.get("decision_id") == decision_id), None)

    if not decision:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

    if isinstance(decision, dict):
        return {
            "id": decision.get("decision_id", "UNKNOWN"),
            "timestamp": decision.get("timestamp", datetime.utcnow().isoformat()),
            "strategy": decision.get("strategy"),
            "instrument": decision.get("instrument"),
            "action": decision.get("action"),
            "confidence": decision.get("confidence"),
            "status": decision.get("status", "PENDING"),
            "setupId": decision.get("setup_id"),
            "riskAssessment": decision.get("risk_assessment", {}),
            "executionDetails": decision.get("execution_details")
        }

    return decision
