from typing import Dict, List
from ...core.event_bus import event_bus
from ...levels.engine import LevelEngine
from ...market_data.models import Tick
from .support_rejection import SupportRejectionStrategy
from .resistance_rejection import ResistanceRejectionStrategy
from .resistance_breakout import ResistanceBreakoutStrategy
from .support_breakdown import SupportBreakdownStrategy
from .liquidity_sweep import LiquiditySweepStrategy
from .level_flip import LevelFlipStrategy
from .vwap_level_confluence import VwapLevelConfluenceStrategy
from .range_level_strategy import RangeLevelStrategy

class LevelStrategyEngine:
    def __init__(self, level_engine: LevelEngine):
        self.level_engine = level_engine
        self.strategies = [
            SupportRejectionStrategy(),
            ResistanceRejectionStrategy(),
            ResistanceBreakoutStrategy(),
            SupportBreakdownStrategy(),
            LiquiditySweepStrategy(),
            LevelFlipStrategy(),
            VwapLevelConfluenceStrategy(),
            RangeLevelStrategy()
        ]

    def start(self):
        event_bus.subscribe("MARKET_TICK", self.process_tick)

    async def process_tick(self, tick: Tick):
        inst = tick.instrument
        levels = self.level_engine.active_levels.get(inst, [])
        for strategy in self.strategies:
            await strategy.evaluate(tick, levels)
