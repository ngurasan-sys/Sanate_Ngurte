from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from typing import List, Dict
import logging
from ...core.websocket import websocket_manager

logger = logging.getLogger(__name__)
router = APIRouter()

# The global instance shouldn't be relied upon. We need a way to pass the level_engine to the router.
# Let's create a dependency injection setup for router if needed, or simply hold the reference.
_level_engine = None

def get_level_engine():
    global _level_engine
    return _level_engine

def set_level_engine(engine):
    global _level_engine
    _level_engine = engine

@router.get("/api/v1/levels")
def get_all_levels():
    engine = get_level_engine()
    if not engine:
        return {}
    return {k: [l.model_dump() for l in v] for k, v in engine.active_levels.items()}

@router.get("/api/v1/levels/{instrument}")
def get_levels(instrument: str, limit: int = Query(50, ge=1, le=200)):
    engine = get_level_engine()
    if not engine:
        return []
    return [l.model_dump() for l in engine.active_levels.get(instrument, [])][:limit]

@router.get("/api/v1/levels/{instrument}/support")
def get_support_levels(instrument: str, limit: int = Query(50, ge=1, le=200)):
    engine = get_level_engine()
    if not engine:
        return []
    return [
        l.model_dump()
        for l in engine.active_levels.get(instrument, [])
        if l.level_type == "Support"
    ][:limit]

@router.get("/api/v1/levels/{instrument}/resistance")
def get_resistance_levels(instrument: str, limit: int = Query(50, ge=1, le=200)):
    engine = get_level_engine()
    if not engine:
        return []
    return [
        l.model_dump()
        for l in engine.active_levels.get(instrument, [])
        if l.level_type == "Resistance"
    ][:limit]

