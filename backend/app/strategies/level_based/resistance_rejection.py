from .base import BaseLevelStrategy

class ResistanceRejectionStrategy(BaseLevelStrategy):
    def __init__(self):
        super().__init__("RESISTANCE_REJECTION")

    async def evaluate(self, tick, levels):
        for level in levels:
            if level.level_type == "Resistance":
                if level.zone_low * 0.998 <= tick.price <= level.zone_high:
                    await self.emit_signal(
                        instrument=tick.instrument,
                        direction="BEARISH",
                        level_id=level.level_id,
                        confidence=82.0,
                        evidence=f"Price {tick.price} rejected at resistance {level.price}"
                    )
