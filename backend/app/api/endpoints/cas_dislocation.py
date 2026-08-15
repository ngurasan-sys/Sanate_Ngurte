import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.strategies.cas_dislocation.config_state import cas_config_state
from backend.app.strategies.cas_dislocation.engine import CASExecutionError, cas_dislocation_engine
from backend.app.strategies.cas_dislocation.models import CASConfigError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cas-dislocation", tags=["cas-dislocation"])


class ConfigureRequest(BaseModel):
    underlying: str
    lots: int
    max_hold_seconds: int = 90
    min_score_to_alert: int = 60
    min_score_to_execute: int = 85
    auto_execute: bool = False


@router.get("/config")
async def get_config():
    return cas_config_state.get()


@router.post("/configure")
async def configure(request: ConfigureRequest):
    try:
        return cas_config_state.configure(
            underlying=request.underlying,
            lots=request.lots,
            max_hold_seconds=request.max_hold_seconds,
            min_score_to_alert=request.min_score_to_alert,
            min_score_to_execute=request.min_score_to_execute,
            auto_execute=request.auto_execute,
        )
    except CASConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/enable")
async def enable():
    return cas_config_state.enable()


@router.post("/disable")
async def disable():
    return cas_config_state.disable()


@router.get("/reading")
async def get_reading():
    return cas_dislocation_engine.latest_reading


@router.get("/positions")
async def list_positions():
    return list(cas_dislocation_engine.positions.values())


@router.post("/execute")
async def execute_current_signal():
    """The [EXECUTE] button: manually confirm the currently-displayed
    signal, independent of the auto_execute config toggle."""
    try:
        return await cas_dislocation_engine.execute_current_signal()
    except CASExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/abort/{position_id}")
async def abort_position(position_id: str):
    """The [ABORT] button: close an active position immediately, ahead
    of its max_hold_seconds auto-exit."""
    try:
        return await cas_dislocation_engine.close_position_manually(position_id)
    except CASExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
