"""Simulated Level 2 tick generator for the Order Flow Footprint Chart
module.

Why a mock feed exists here, deliberately, unlike the rest of this
codebase (which treats fabricated market data as a hard error — see
backtest/engine.py, algo_config.py etc.): the currently-connected Upstox
stream runs in 'ltpc' mode against index spot instruments (upstox_v3.py)
— no market depth, no volume, no futures contracts at all. Getting real
Level 2 depth for NIFTY/SENSEX/BANKNIFTY *futures* would mean subscribing
in Upstox's 'full'/'full_d30' mode against real futures instrument keys,
a separate live-integration task this module doesn't attempt. Until that
exists, this generator is the only tick source for the footprint chart.

To keep that honest:
- Ticks publish on their own "footprint_mock_tick" event, never
  "MARKET_TICK" — so this simulated data can never leak into any real
  strategy engine that listens to the live feed.
- Every downstream consumer (see footprint.py endpoints, the frontend)
  is expected to label this as simulated data, not live pricing.
"""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Dict

from backend.app.core.event_bus import event_bus

logger = logging.getLogger(__name__)

# Starting reference prices — arbitrary but in the right ballpark, purely
# to seed a plausible-looking random walk.
_SEED_PRICES: Dict[str, float] = {
    "NIFTY FUT": 24_550.0,
    "BANKNIFTY FUT": 51_800.0,
    "SENSEX FUT": 80_400.0,
}

TICK_SIZE = 0.05
_LOT_SIZE_HINT = {"NIFTY FUT": 25, "BANKNIFTY FUT": 15, "SENSEX FUT": 10}


class MockFootprintFeed:
    """Runs one independent random-walk price process per instrument,
    biasing volume/direction in short bursts so imbalance zones actually
    show up for the frontend to render — a flat coin-flip walk would
    rarely produce the 200-500% diagonal imbalances the UI is built to
    highlight.
    """

    def __init__(self, tick_interval_seconds: float = 0.2):
        self.tick_interval_seconds = tick_interval_seconds
        self.running = False
        self._task: asyncio.Task | None = None
        self._prices: Dict[str, float] = dict(_SEED_PRICES)
        # Per-instrument burst state: remaining ticks and biased direction.
        self._burst: Dict[str, Dict[str, object]] = {
            k: {"ticks_left": 0, "direction": "AGGRESSIVE_BUY"} for k in _SEED_PRICES
        }

    def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("MockFootprintFeed started (simulated ticks — see module docstring)")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()

    async def _run_loop(self):
        try:
            while self.running:
                for instrument_key in _SEED_PRICES:
                    tick = self._generate_tick(instrument_key)
                    await event_bus.publish("footprint_mock_tick", tick)
                await asyncio.sleep(self.tick_interval_seconds)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("MockFootprintFeed loop crashed")

    def _generate_tick(self, instrument_key: str) -> dict:
        burst = self._burst[instrument_key]
        if burst["ticks_left"] <= 0 and random.random() < 0.08:
            # Start a new burst: 3-8 consecutive same-direction aggressive
            # trades, growing volume — this is what produces a visible
            # diagonal/stacked imbalance in the footprint.
            burst["ticks_left"] = random.randint(3, 8)
            burst["direction"] = random.choice(["AGGRESSIVE_BUY", "AGGRESSIVE_SELL"])

        if burst["ticks_left"] > 0:
            direction = burst["direction"]
            burst["ticks_left"] -= 1
            volume = random.randint(150, 900) * _LOT_SIZE_HINT[instrument_key]
            drift = TICK_SIZE if direction == "AGGRESSIVE_BUY" else -TICK_SIZE
        else:
            direction = random.choice(["AGGRESSIVE_BUY", "AGGRESSIVE_SELL"])
            volume = random.randint(1, 50) * _LOT_SIZE_HINT[instrument_key]
            drift = random.choice([-1, 0, 1]) * TICK_SIZE

        price = round(self._prices[instrument_key] + drift, 2)
        # Snap to the instrument's tick size so footprint price levels
        # line up cleanly instead of drifting into float noise.
        price = round(price / TICK_SIZE) * TICK_SIZE
        self._prices[instrument_key] = price

        return {
            "instrument_key": instrument_key,
            "price": price,
            "volume": volume,
            "direction": direction,
            "timestamp": datetime.now(timezone.utc),
        }


mock_footprint_feed = MockFootprintFeed()
