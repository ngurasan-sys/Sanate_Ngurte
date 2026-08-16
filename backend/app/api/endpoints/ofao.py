import logging

from fastapi import APIRouter, HTTPException

from backend.app.strategies.order_flow_absorption.config import OFAOConfig, OFAOConfigError
from backend.app.strategies.order_flow_absorption.engine import ofao_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ofao", tags=["ofao"])


@router.get("/config")
async def get_config():
    return ofao_engine.config


@router.post("/configure")
async def configure(request: OFAOConfig):
    try:
        return ofao_engine.configure(request)
    except OFAOConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/enable")
async def enable():
    return ofao_engine.enable()


@router.post("/disable")
async def disable():
    return ofao_engine.disable()


@router.get("/state/{instrument_key}")
async def get_state(instrument_key: str):
    snapshot = ofao_engine.get_snapshot(instrument_key)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No OFAO state yet for this instrument.")
    return snapshot
