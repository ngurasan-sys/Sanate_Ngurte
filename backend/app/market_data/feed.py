import asyncio
import random
from datetime import datetime
from pytz import timezone
from .models import Tick
from .processor import TickProcessor

ist = timezone('Asia/Kolkata')

class MockFeed:
    def __init__(self, processor: TickProcessor):
        self.running = False
        self.instruments = ["NIFTY", "BANKNIFTY"]
        self.last_price = {"NIFTY": 25000.0, "BANKNIFTY": 52000.0}
        self.processor = processor

    async def start(self):
        self.running = True
        while self.running:
            for inst in self.instruments:
                change = random.uniform(-5.0, 5.0)
                self.last_price[inst] += change
                tick = Tick(
                    instrument=inst,
                    price=round(self.last_price[inst], 2),
                    volume=random.uniform(10, 100),
                    timestamp=datetime.now(ist)
                )
                await self.processor.process(tick)
            await asyncio.sleep(1)

    def stop(self):
        self.running = False
