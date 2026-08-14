from .base import BaseLevelStrategy
class RangeLevelStrategy(BaseLevelStrategy):
    def __init__(self):
        super().__init__("RANGE_LEVEL")
    async def evaluate(self, tick, levels):
        pass
