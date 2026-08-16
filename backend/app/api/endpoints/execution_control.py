"""Runtime control surface for live order execution.

Exposes the second arm switch (see execution.runtime_state) and the risk
kill switch to the frontend. Never changes EXECUTION_MODE itself —
that env var is the first, fixed-at-process-start switch and stays
outside the frontend's reach on purpose.
"""

import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.engines.risk import risk_engine
from backend.app.execution.order_gateway import resolve_mode
from backend.app.execution.runtime_state import execution_runtime_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/execution", tags=["execution-control"])

ARM_CONFIRMATION_PHRASE = "ARM LIVE TRADING"


class ArmRequest(BaseModel):
    confirm: str
    note: str | None = None


class HaltRequest(BaseModel):
    reason: str


def _status_payload() -> dict:
    env_mode = (os.environ.get("EXECUTION_MODE") or "DRY_RUN").strip().upper()
    arm = execution_runtime_state.snapshot()
    limits = risk_engine.limits
    state = risk_engine.state

    return {
        "env_mode": env_mode,
        "resolved_mode": resolve_mode().value,
        "armed": arm.armed,
        "armed_at": arm.armed_at.isoformat() if arm.armed_at else None,
        "armed_note": arm.note,
        "halted_reason": state.halted_reason,
        "risk_limits": {
            "max_quantity_per_order": limits.max_quantity_per_order,
            "max_open_positions": limits.max_open_positions,
            "max_daily_loss": limits.max_daily_loss,
            "max_daily_orders": limits.max_daily_orders,
            "market_open": limits.market_open.isoformat(),
            "market_close": limits.market_close.isoformat(),
            "allow_trading": limits.allow_trading,
        },
        "risk_state": {
            "open_positions": state.open_positions,
            "realized_pnl_today": state.realized_pnl_today,
            "orders_placed_today": state.orders_placed_today,
        },
    }


@router.get("/status")
async def get_status():
    return _status_payload()


@router.post("/arm")
async def arm_live_trading(req: ArmRequest):
    if req.confirm != ARM_CONFIRMATION_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f"Confirmation phrase must be exactly '{ARM_CONFIRMATION_PHRASE}'.",
        )
    execution_runtime_state.arm(note=req.note)
    logger.warning("Runtime LIVE-trading arm switch ENABLED via frontend. note=%r", req.note)
    return _status_payload()


@router.post("/disarm")
async def disarm_live_trading():
    execution_runtime_state.disarm()
    logger.info("Runtime LIVE-trading arm switch disabled via frontend.")
    return _status_payload()


@router.post("/halt")
async def halt_trading(req: HaltRequest):
    risk_engine.halt(req.reason)
    logger.warning("Risk kill switch HALTED via frontend. reason=%r", req.reason)
    return _status_payload()


@router.post("/resume")
async def resume_trading():
    risk_engine.resume()
    logger.info("Risk kill switch resumed via frontend.")
    return _status_payload()
