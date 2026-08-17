from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

# Will be injected at startup with list of available strategy engines
_strategy_registry: Dict[str, Dict[str, Any]] = {}

def register_strategy(strategy_id: str, name: str, description: str, engine=None):
    """Register a strategy engine for listing via API."""
    _strategy_registry[strategy_id] = {
        "id": strategy_id,
        "name": name,
        "description": description,
        "enabled": True,
        "status": "ACTIVE",
        "engine": engine  # Backend reference, not exposed in JSON
    }

def set_strategy_registry(registry: Dict[str, Dict[str, Any]]):
    """Inject the full strategy registry (alternative to individual register calls)."""
    global _strategy_registry
    _strategy_registry = registry

@router.get("/api/v1/strategies")
def list_strategies():
    """
    List all available strategies with metadata.
    Returns: [ { id, name, description, enabled, status, signal, confidence, pnl, trades, winRate, readiness } ]
    """
    if not _strategy_registry:
        return {
            "strategies": [],
            "count": 0,
            "timestamp": datetime.utcnow().isoformat()
        }

    strategies = []
    for strategy_id, meta in _strategy_registry.items():
        engine = meta.get("engine")

        # Build response for this strategy
        strategy_info = {
            "id": strategy_id,
            "name": meta.get("name", strategy_id),
            "description": meta.get("description", ""),
            "enabled": meta.get("enabled", True),
            "status": meta.get("status", "UNKNOWN"),
            "signal": None,  # Updated by real-time engine state
            "confidence": None,
            "pnl": None,
            "tradeCount": 0,
            "winRate": None,
            "readiness": "PENDING"  # or READY, ERROR, etc.
        }

        # If engine exists, fetch its current state
        if engine:
            try:
                # Different engines have different state structures
                # Try to extract common fields
                if hasattr(engine, "positions"):
                    active_positions = [p for p in engine.positions.values() if p and p.get("is_active")]
                    strategy_info["tradeCount"] = len(active_positions)
                    if active_positions:
                        strategy_info["readiness"] = "ACTIVE"
                        strategy_info["signal"] = active_positions[0].get("signal", None)
                        strategy_info["confidence"] = active_positions[0].get("confidence")
                        strategy_info["pnl"] = active_positions[0].get("pnl")

                if hasattr(engine, "config"):
                    strategy_info["readiness"] = "READY" if engine.config else "PENDING"

            except Exception as e:
                logger.warning(f"Failed to extract state from {strategy_id}: {e}")

        strategies.append(strategy_info)

    return {
        "strategies": strategies,
        "count": len(strategies),
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/api/v1/strategies/{strategy_id}")
def get_strategy(strategy_id: str):
    """Fetch details of a single strategy."""
    if strategy_id not in _strategy_registry:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")

    meta = _strategy_registry[strategy_id]
    engine = meta.get("engine")

    info = {
        "id": strategy_id,
        "name": meta.get("name", strategy_id),
        "description": meta.get("description", ""),
        "enabled": meta.get("enabled", True),
        "status": meta.get("status", "UNKNOWN"),
        "signal": None,
        "confidence": None,
        "pnl": None,
        "tradeCount": 0,
        "winRate": None,
        "readiness": "PENDING",
        "positions": []
    }

    if engine and hasattr(engine, "positions"):
        positions = engine.positions.values()
        info["positions"] = [p for p in positions if p]  # Non-null positions
        info["tradeCount"] = len([p for p in positions if p and p.get("is_active")])

    return info
