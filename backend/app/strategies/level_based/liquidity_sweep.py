from .base import BaseLevelStrategy
class LiquiditySweepStrategy(BaseLevelStrategy):
    def __init__(self):
        super().__init__("LIQUIDITY_SWEEP")
    async def evaluate(self, tick, levels):
        pass
