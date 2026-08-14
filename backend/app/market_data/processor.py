from datetime import datetime
from typing import Dict
from .models import Tick, Candle
from ..core.event_bus import event_bus

class CandleAggregator:
    def __init__(self, timeframe_minutes: int = 5):
        self.timeframe_minutes = timeframe_minutes
        self.current_candles: Dict[str, Candle] = {}
        self.cumulative_volume_price: Dict[str, float] = {}
        self.cumulative_volume: Dict[str, float] = {}

    def get_candle_start(self, dt: datetime) -> datetime:
        minute = (dt.minute // self.timeframe_minutes) * self.timeframe_minutes
        return dt.replace(minute=minute, second=0, microsecond=0)

    async def process_tick(self, tick: Tick):
        candle_start = self.get_candle_start(tick.timestamp)
        instrument = tick.instrument

        if instrument not in self.cumulative_volume_price:
            self.cumulative_volume_price[instrument] = 0.0
            self.cumulative_volume[instrument] = 0.0

        if instrument in self.current_candles:
            current = self.current_candles[instrument]
            if candle_start > current.timestamp:
                current.is_closed = True
                await event_bus.publish("CANDLE_CLOSED", current)

                self.current_candles[instrument] = Candle(
                    instrument=instrument,
                    timeframe=f"{self.timeframe_minutes}m",
                    timestamp=candle_start,
                    open=tick.price,
                    high=tick.price,
                    low=tick.price,
                    close=tick.price,
                    volume=tick.volume or 0.0
                )
            else:
                current.high = max(current.high, tick.price)
                current.low = min(current.low, tick.price)
                current.close = tick.price
                current.volume += tick.volume or 0.0
        else:
            self.current_candles[instrument] = Candle(
                instrument=instrument,
                timeframe=f"{self.timeframe_minutes}m",
                timestamp=candle_start,
                open=tick.price,
                high=tick.price,
                low=tick.price,
                close=tick.price,
                volume=tick.volume or 0.0
            )

        if tick.volume:
            self.cumulative_volume_price[instrument] += tick.price * tick.volume
            self.cumulative_volume[instrument] += tick.volume
            if self.cumulative_volume[instrument] > 0:
                self.current_candles[instrument].vwap = self.cumulative_volume_price[instrument] / self.cumulative_volume[instrument]

class TickProcessor:
    def __init__(self):
        self.aggregators = [
            CandleAggregator(timeframe_minutes=3),
            CandleAggregator(timeframe_minutes=5),
            CandleAggregator(timeframe_minutes=15)
        ]

    async def process(self, tick: Tick):
        await event_bus.publish("MARKET_TICK", tick)
        for aggregator in self.aggregators:
            await aggregator.process_tick(tick)
