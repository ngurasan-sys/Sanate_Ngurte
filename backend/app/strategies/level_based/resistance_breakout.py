from .base import BaseLevelStrategy
class ResistanceBreakoutStrategy(BaseLevelStrategy):
    def __init__(self):
        super().__init__("RESISTANCE_BREAKOUT")
    async def evaluate(self, tick, levels):
        pass
