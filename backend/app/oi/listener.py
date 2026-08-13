import asyncio
from .models import OITick
from .engine import OIEngine

class OIDataListener:
    """Listens to market data streams and feeds the OIEngine"""
    def __init__(self, engine: OIEngine):
        self.engine = engine
        self.running = False

    async def start(self):
        self.running = True

    async def stop(self):
        self.running = False

    async def on_tick(self, tick: OITick):
        if self.running:
            self.engine.process_tick(tick)