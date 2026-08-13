from .base import BaseLevelStrategy
class LevelFlipStrategy(BaseLevelStrategy):
    def __init__(self):
        super().__init__("LEVEL_FLIP")
    async def evaluate(self, tick, levels):
        pass
