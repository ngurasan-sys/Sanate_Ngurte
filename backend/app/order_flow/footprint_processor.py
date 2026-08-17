"""Bridges the mock tick feed (mock_feed.py) into FootprintCandleAggregator
and broadcasts the resulting candles to the frontend every 500ms, per the
module's spec. Mirrors the coalesced-broadcast pattern already used by
OrderFlowTickProcessor (tick_processor.py) — a shared aggregator updated
on every tick, snapshotted and published on a fixed interval rather than
per-tick, so a fast tick stream doesn't flood the WebSocket.
"""

import asyncio
import logging
from typing import Optional

from backend.app.core.event_bus import event_bus

from .footprint_candle import FootprintCandleAggregator, TIMEFRAME_SECONDS

logger = logging.getLogger(__name__)

# Every tracked timeframe gets its own candle built in parallel from the
# same tick stream — the frontend's timeframe selector just switches
# which one it reads, no backend round-trip needed to change timeframe.
TRACKED_TIMEFRAMES = list(TIMEFRAME_SECONDS.keys())


class FootprintProcessor:
    def __init__(self, broadcast_interval_seconds: float = 0.5):
        self.aggregator = FootprintCandleAggregator()
        self.broadcast_interval_seconds = broadcast_interval_seconds
        self.running = False
        self._broadcast_task: Optional[asyncio.Task] = None
        self._dirty_instruments: set[str] = set()
        # Only mock_feed.py's "footprint_mock_tick" event is subscribed to
        # below — no real Level-2 futures feed exists yet (see
        # mock_feed.py's module docstring). This is the single source of
        # truth OFAOEngine's LIVE-execution gate (risk.py) reads to decide
        # whether OFAO is allowed to place a real order. Flip this to
        # "REAL" only once a genuine Level-2 tick source is wired in and
        # publishing here instead of/alongside the mock feed.
        self.data_source: str = "MOCK"

    def start(self):
        if self.running:
            return
        self.running = True
        event_bus.subscribe("footprint_mock_tick", self._on_tick)
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        logger.info("FootprintProcessor started")

    def stop(self):
        self.running = False
        if self._broadcast_task:
            self._broadcast_task.cancel()

    def set_imbalance_ratio_pct(self, ratio_pct: float) -> None:
        self.aggregator.set_imbalance_ratio_pct(ratio_pct)

    async def _on_tick(self, tick: dict):
        try:
            instrument_key = tick["instrument_key"]
            for timeframe in TRACKED_TIMEFRAMES:
                self.aggregator.process_tick(
                    instrument_key, tick["price"], tick["volume"], tick["direction"],
                    tick["timestamp"], timeframe,
                )
            self._dirty_instruments.add(instrument_key)
        except Exception:
            logger.debug("Error processing footprint tick", exc_info=True)

    async def _broadcast_loop(self):
        try:
            while self.running:
                await asyncio.sleep(self.broadcast_interval_seconds)
                if not self._dirty_instruments:
                    continue

                for instrument_key in list(self._dirty_instruments):
                    payload = {
                        "instrument_key": instrument_key,
                        "candles": {
                            timeframe: candle.model_dump(mode="json")
                            for timeframe in TRACKED_TIMEFRAMES
                            if (candle := self.aggregator.get_current(instrument_key, timeframe)) is not None
                        },
                    }
                    await event_bus.publish("footprint_candles", payload)

                self._dirty_instruments.clear()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("FootprintProcessor broadcast loop crashed")


footprint_processor = FootprintProcessor()
