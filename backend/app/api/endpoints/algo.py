import logging
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/algo", tags=["algo"])

class StatusUpdate(BaseModel):
    status: str

@router.post("/engine/status")
async def update_engine_status(update: StatusUpdate):
    logger.info(f"Algo Engine status updated to: {update.status}")
    from backend.app.core.event_bus import event_bus
    await event_bus.publish("ALGO_STATUS", {"status": update.status})
    return {"status": update.status}

class ModeUpdate(BaseModel):
    mode: str

@router.post("/execution/mode")
async def update_execution_mode(update: ModeUpdate):
    logger.info(f"Execution mode updated to: {update.mode}")
    # Update logic here
    return {"mode": update.mode}
