from typing import List
from .models import Level
from ..market_data.models import Candle

class BaseDetector:
    def detect(self, candles: List[Candle], current_levels: List[Level]) -> List[Level]:
        raise NotImplementedError
