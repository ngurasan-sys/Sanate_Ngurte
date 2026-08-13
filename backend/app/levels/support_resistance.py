from .detector import BaseDetector
from .models import Level
from ..market_data.models import Candle
from typing import List
import uuid

class SupportResistanceDetector(BaseDetector):
    def detect(self, candles: List[Candle], current_levels: List[Level]) -> List[Level]:
        new_levels = []
        if len(candles) < 3:
            return new_levels

        for i in range(1, len(candles) - 1):
            prev_c = candles[i-1]
            curr_c = candles[i]
            next_c = candles[i+1]

            if curr_c.high > prev_c.high and curr_c.high > next_c.high:
                level = Level(
                    level_id=f"lvl_{uuid.uuid4().hex[:8]}",
                    instrument=curr_c.instrument,
                    price=curr_c.high,
                    zone_low=curr_c.high * 0.9995,
                    zone_high=curr_c.high * 1.0005,
                    level_type="Resistance",
                    timeframe=curr_c.timeframe,
                    source="SwingStructure",
                    created_at=curr_c.timestamp,
                    updated_at=curr_c.timestamp
                )
                new_levels.append(level)

            if curr_c.low < prev_c.low and curr_c.low < next_c.low:
                level = Level(
                    level_id=f"lvl_{uuid.uuid4().hex[:8]}",
                    instrument=curr_c.instrument,
                    price=curr_c.low,
                    zone_low=curr_c.low * 0.9995,
                    zone_high=curr_c.low * 1.0005,
                    level_type="Support",
                    timeframe=curr_c.timeframe,
                    source="SwingStructure",
                    created_at=curr_c.timestamp,
                    updated_at=curr_c.timestamp
                )
                new_levels.append(level)

        return new_levels
