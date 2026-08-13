from .base import BaseLevelStrategy

class SupportRejectionStrategy(BaseLevelStrategy):
    def __init__(self):
        super().__init__("SUPPORT_REJECTION")

    async def evaluate(self, tick, levels):
        for level in levels:
            if level.level_type == "Support":
                # Basic mock logic for rejection: if price nears support and bounces
                if level.zone_low <= tick.price <= level.zone_high * 1.002:
                    await self.emit_signal(
                        instrument=tick.instrument,
                        direction="BULLISH",
                        level_id=level.level_id,
                        confidence=85.0,
                        evidence=f"Price {tick.price} rejected at support {level.price}"
                    )
