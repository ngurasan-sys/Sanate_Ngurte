from pydantic import BaseModel
from datetime import datetime

class Level(BaseModel):
    level_id: str
    instrument: str
    price: float
    zone_low: float
    zone_high: float
    level_type: str
    timeframe: str
    strength: float = 0.0
    confidence: float = 0.0
    touch_count: int = 0
    rejection_count: int = 0
    breakout_count: int = 0
    volume_confirmation: bool = False
    liquidity_score: float = 0.0
    distance_from_price: float = 0.0
    age: int = 0
    source: str
    created_at: datetime
    updated_at: datetime
    active: bool = True
