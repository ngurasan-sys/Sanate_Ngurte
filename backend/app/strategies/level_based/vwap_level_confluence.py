from .base import BaseLevelStrategy
class VwapLevelConfluenceStrategy(BaseLevelStrategy):
    def __init__(self):
        super().__init__("VWAP_LEVEL_CONFLUENCE")
    async def evaluate(self, tick, levels):
        pass
