from fastapi import APIRouter, HTTPException
from backend.app.order_flow.tick_processor import order_flow_processor

router = APIRouter(prefix="/api/v1/order-flow", tags=["order-flow"])

@router.get("/{instrument_key}")
async def get_order_flow(instrument_key: str):
    state = order_flow_processor.engine.get_state(instrument_key)
    if state is None:
        raise HTTPException(status_code=404, detail="Order flow state not found")
    return state.model_dump()
