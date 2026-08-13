from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class Tick(BaseModel):
    instrument: str
    price: float
    volume: Optional[float] = 0.0
    timestamp: datetime
    is_trade: bool = True

class Candle(BaseModel):
    instrument: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: Optional[float] = None
    is_closed: bool = False
