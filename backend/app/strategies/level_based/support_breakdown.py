from .base import BaseLevelStrategy
class SupportBreakdownStrategy(BaseLevelStrategy):
    def __init__(self):
        super().__init__("SUPPORT_BREAKDOWN")
    async def evaluate(self, tick, levels):
        pass
