from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any
from backend.app.engines.greeks_engine import GreeksEngine

router = APIRouter(prefix="/api/v1/greeks", tags=["greeks"])
engine = GreeksEngine()

class GreekCalculateRequest(BaseModel):
    instrument: str
    underlying: str
    expiry: str
    strike: float
    option_type: str
    spot_price: float
    option_price: float
    time_to_expiry: float

@router.post("/calculate")
async def calculate_greeks(request: GreekCalculateRequest):
    # This is a sample REST entrypoint to trigger calculation via HTTP
    await engine.calculate_and_publish(request.model_dump())
    return {"status": "calculated"}
