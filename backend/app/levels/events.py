from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any

class LevelEvent(BaseModel):
    event_id: str
    level_id: str
    event_type: str
    timestamp: datetime
    price: float
    details: Dict[str, Any]

class LiquidityEvent(BaseModel):
    event_id: str
    instrument: str
    price: float
    side: str
    volume: float
    timestamp: datetime
