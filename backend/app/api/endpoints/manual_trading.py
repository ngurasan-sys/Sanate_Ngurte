import logging

from fastapi import APIRouter, HTTPException

from backend.app.market_data.lot_sizes import LOT_SIZES
from backend.app.strategies.manual_trading.engine import (
    ManualTradingError,
    manual_trading_engine,
)
from backend.app.strategies.manual_trading.models import ManualOrderRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/manual-trading", tags=["manual-trading"])


@router.get("/lot-sizes")
async def get_lot_sizes():
    """Lets the frontend compute Qty = lots x lot_size live, without
    hardcoding lot sizes client-side."""
    return LOT_SIZES


@router.get("/positions")
async def list_positions():
    return list(manual_trading_engine.positions.values())


@router.post("/order")
async def place_manual_order(request: ManualOrderRequest):
    try:
        return await manual_trading_engine.place_order(request)
    except ManualTradingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/pyramid/{position_id}")
async def add_pyramid_lot(position_id: str):
    try:
        return await manual_trading_engine.add_pyramid(position_id)
    except ManualTradingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/close/{position_id}")
async def close_manual_position(position_id: str):
    try:
        return await manual_trading_engine.close_position(position_id)
    except ManualTradingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
