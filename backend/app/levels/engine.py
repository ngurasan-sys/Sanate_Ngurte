from typing import Dict, List
from ..core.event_bus import event_bus
from .models import Level
from ..market_data.models import Candle
from .support_resistance import SupportResistanceDetector
from .confluence import ConfluenceDetector

class LevelEngine:
    def __init__(self):
        self.active_levels: Dict[str, List[Level]] = {}
        self.history: Dict[str, List[Candle]] = {}
        self.detectors = [SupportResistanceDetector(), ConfluenceDetector()]

    def start(self):
        event_bus.subscribe("CANDLE_CLOSED", self.process_candle)

    async def process_candle(self, candle: Candle):
        inst = candle.instrument
        if inst not in self.history:
            self.history[inst] = []
        if inst not in self.active_levels:
            self.active_levels[inst] = []

        self.history[inst].append(candle)
        if len(self.history[inst]) > 100:
            self.history[inst].pop(0)

        new_levels = []
        # Only evaluate the last few candles to avoid re-evaluating the entire history for efficiency
        # SupportResistanceDetector needs at least 3 candles.
        eval_window = self.history[inst][-5:] if len(self.history[inst]) >= 5 else self.history[inst]

        for detector in self.detectors:
            new_levels.extend(detector.detect(eval_window, self.active_levels[inst]))

        for level in new_levels:
            is_duplicate = any(
                abs(existing.price - level.price) < existing.price * 0.001
                for existing in self.active_levels[inst]
            )
            if not is_duplicate:
                self.active_levels[inst].append(level)
                await event_bus.publish("LEVEL_CREATED", level.model_dump())
