import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Literal, Optional

from backend.app.engines.algo_config import AlgoConfigError, algo_config_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/algo-config", tags=["algo-config"])


class ConfigureRequest(BaseModel):
    mode: Literal["SYSTEM", "MANUAL"]
    underlying: Optional[str] = None
    capital: Optional[float] = None
    lot_schedule: List[int] = []
    stop_loss_pct: Optional[float] = None
    target_pct: Optional[float] = None


@router.get("/status")
async def get_status():
    return algo_config_state.get()


@router.post("/configure")
async def configure(request: ConfigureRequest):
    """Reconfiguring always disarms — see AlgoConfigState.configure — so
    changing numbers can never silently keep a different, stale budget armed.
    """
    try:
        return algo_config_state.configure(
            mode=request.mode,
            underlying=request.underlying,
            capital=request.capital,
            lot_schedule=request.lot_schedule,
            stop_loss_pct=request.stop_loss_pct,
            target_pct=request.target_pct,
        )
    except AlgoConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/enable")
async def enable():
    return algo_config_state.enable()


@router.post("/disable")
async def disable():
    return algo_config_state.disable()
