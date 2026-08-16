from typing import Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.order_flow.footprint_candle import TIMEFRAME_SECONDS
from backend.app.order_flow.footprint_processor import footprint_processor
from backend.app.order_flow.mock_feed import _SEED_PRICES

router = APIRouter(prefix="/api/v1/footprint", tags=["footprint"])


@router.get("/instruments")
async def list_instruments() -> List[str]:
    return list(_SEED_PRICES.keys())


@router.get("/timeframes")
async def list_timeframes() -> List[str]:
    return list(TIMEFRAME_SECONDS.keys())


@router.get("/{instrument_key}/{timeframe}")
async def get_current_candle(instrument_key: str, timeframe: str):
    if timeframe not in TIMEFRAME_SECONDS:
        raise HTTPException(status_code=422, detail=f"Unknown timeframe {timeframe!r}. Available: {list(TIMEFRAME_SECONDS)}.")
    candle = footprint_processor.aggregator.get_current(instrument_key, timeframe)
    if candle is None:
        raise HTTPException(status_code=404, detail="No candle data yet for this instrument/timeframe.")
    return candle.model_dump(mode="json")


@router.get("/{instrument_key}/{timeframe}/history")
async def get_candle_history(instrument_key: str, timeframe: str):
    if timeframe not in TIMEFRAME_SECONDS:
        raise HTTPException(status_code=422, detail=f"Unknown timeframe {timeframe!r}. Available: {list(TIMEFRAME_SECONDS)}.")
    history = footprint_processor.aggregator.get_history(instrument_key, timeframe)
    return [c.model_dump(mode="json") for c in history]


class ImbalanceRatioRequest(BaseModel):
    ratio_pct: float  # 200-500, per the UI's Imbalance Ratio Dial


@router.post("/imbalance-ratio")
async def set_imbalance_ratio(request: ImbalanceRatioRequest) -> Dict[str, float]:
    if not (100.0 <= request.ratio_pct <= 1000.0):
        raise HTTPException(status_code=422, detail="ratio_pct must be between 100 and 1000.")
    footprint_processor.set_imbalance_ratio_pct(request.ratio_pct)
    return {"ratio_pct": request.ratio_pct}
