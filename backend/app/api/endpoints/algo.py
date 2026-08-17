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


# NOTE: there used to be a POST /execution/mode endpoint here that only
# logged the requested mode and echoed it back — it never touched
# execution_runtime_state, EXECUTION_MODE, or anything RiskEngine/
# OrderGateway actually read, so toggling it in the UI changed nothing
# about what happened to an order. Removed in favor of the real arm
# switch at /api/v1/execution/arm and /disarm (execution_control.py),
# which the frontend's Algo Dashboard now calls directly.
