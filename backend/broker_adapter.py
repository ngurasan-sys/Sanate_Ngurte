import asyncio
import json
import random
import time
from typing import List, Dict, Any
from datetime import datetime, timedelta

def generate_historical_data(symbol: str, timeframe: str, from_date: str, to_date: str) -> List[Dict[str, Any]]:
    # Mock historical data generation
    data = []

    # Parse timeframe to minutes
    tf_map = {'1m': 1, '3m': 3, '5m': 5, '15m': 15, '1h': 60, '1D': 1440}
    minutes = tf_map.get(timeframe, 1)

    # Parse dates (simplified)
    # If invalid, default to last 100 bars
    start_time = int(time.time()) - (100 * minutes * 60)
    current_time = start_time

    base_price = 24500.0 if "NIFTY" in symbol else 81000.0

    for _ in range(100):
        open_p = base_price + random.uniform(-10, 10)
        high_p = open_p + random.uniform(0, 20)
        low_p = open_p - random.uniform(0, 20)
        close_p = random.uniform(low_p, high_p)
        volume = random.randint(1000, 50000)
        oi = random.randint(1000000, 5000000)

        data.append({
            "time": current_time,
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": volume,
            "oi": oi
        })

        base_price = close_p
        current_time += minutes * 60

    return data

class LiveTickStream:
    def __init__(self):
        self.clients = set()
        self.active = False
        self._task = None
        self.base_price = 24500.0
        self.base_oi = 4500000

    async def connect(self, websocket):
        self.clients.add(websocket)
        if not self.active:
            self.active = True
            self._task = asyncio.create_task(self._stream_ticks())

    def disconnect(self, websocket):
        self.clients.remove(websocket)
        if not self.clients:
            self.active = False
            if self._task:
                self._task.cancel()
                self._task = None

    async def _stream_ticks(self):
        while self.active:
            await asyncio.sleep(0.5) # Simulate 2 ticks per second

            # Random walk price and OI
            self.base_price += random.uniform(-2, 2)
            self.base_oi += random.randint(-5000, 5000)

            tick = {
                "type": "tick",
                "symbol": "NIFTY",
                "ltp": round(self.base_price, 2),
                "volume": random.randint(10, 100),
                "oi": self.base_oi,
                "timestamp": int(time.time() * 1000)
            }

            dead_clients = set()
            for client in self.clients:
                try:
                    await client.send_text(json.dumps(tick))
                except Exception:
                    dead_clients.add(client)

            for client in dead_clients:
                self.disconnect(client)

tick_stream = LiveTickStream()
