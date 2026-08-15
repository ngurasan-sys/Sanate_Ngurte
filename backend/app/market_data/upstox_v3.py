import asyncio
import logging
from datetime import datetime

try:
    from upstox_client.api_client import ApiClient
    from upstox_client.configuration import Configuration
    from upstox_client.feeder.market_data_streamer_v3 import MarketDataStreamerV3
    UPSTOX_AVAILABLE = True
except ImportError:
    UPSTOX_AVAILABLE = False
    ApiClient = None
    Configuration = None
    MarketDataStreamerV3 = None

from .models import Tick
from .symbols import INDEX_INSTRUMENT_KEYS
from backend.app.core.event_bus import event_bus

logger = logging.getLogger(__name__)

class UpstoxV3Client:
    def __init__(self, api_client: ApiClient = None, instrument_keys=None):
        self.api_client = api_client
        self.subscriptions = set(instrument_keys) if instrument_keys else set()
        # Set in connect(); the SDK delivers messages on a background thread,
        # so _on_message needs a handle on the asyncio loop to dispatch into.
        self._loop = None
        if UPSTOX_AVAILABLE and api_client:
            self.streamer = MarketDataStreamerV3(self.api_client, instrument_keys or [])
            self._wire_handlers()
        else:
            self.streamer = None

    def _wire_handlers(self):
        self.streamer.on("message", self._on_message)
        self.streamer.on("open", self._on_open)
        self.streamer.on("close", self._on_close)
        self.streamer.on("error", self._on_error)

    def configure(self, access_token: str) -> bool:
        """Switch from mock mode into a real live-feed client using a real
        OAuth access token. Safe to call again later (e.g. after a fresh
        login replaces an expired token) — disconnects any existing streamer
        first.

        Returns True if a live streamer was actually built, False if the SDK
        isn't installed and we're staying in mock mode. Callers use this to
        report honestly rather than claiming a live connection."""
        if not UPSTOX_AVAILABLE:
            logger.warning(
                "upstox_client SDK not installed; cannot configure a live feed"
            )
            return False

        if self.streamer:
            try:
                self.streamer.disconnect()
            except Exception as exc:
                logger.warning("Failed to close previous streamer: %s", exc)

        configuration = Configuration()
        configuration.access_token = access_token
        self.api_client = ApiClient(configuration)
        self.streamer = MarketDataStreamerV3(
            self.api_client, list(self.subscriptions)
        )
        self._wire_handlers()
        return True

    async def connect(self):
        # The SDK runs its websocket on its own thread and invokes our
        # callbacks from there, so capture the loop here (while we are
        # provably on it) for _on_message to dispatch back into.
        self._loop = asyncio.get_running_loop()

        if self.streamer:
            # MarketDataStreamerV3 handles auto-reconnect typically, but we call connect
            self.streamer.connect()
        else:
            logger.warning("UpstoxV3Client missing api_client, running in mock mode")

    def _on_open(self):
        logger.info("Connected to Upstox V3 Market Data Feed")

    def _on_close(self, code, reason):
        logger.warning(f"Upstox V3 Connection closed: {code} - {reason}")

    def _on_error(self, error):
        logger.error(f"Upstox V3 Error: {error}")

    def _on_message(self, message):
        # NOTE: this runs on the SDK's websocket thread, not the asyncio loop
        # thread, so asyncio.create_task() is unavailable here — we hand the
        # coroutine to the loop captured in connect() instead.
        try:
            if "feeds" not in message:
                return

            if self._loop is None:
                logger.warning(
                    "Dropping V3 message: no event loop captured yet "
                    "(connect() has not run)"
                )
                return

            for instrument_key, feed in message["feeds"].items():
                asyncio.run_coroutine_threadsafe(
                    self._publish_tick(instrument_key, feed), self._loop
                )
        except Exception as e:
            logger.error(f"Error processing V3 message: {e}")

    async def _publish_tick(self, instrument_key: str, data: dict):
        try:
            # The streamer is constructed with the SDK's default mode 'ltpc',
            # so each Feed carries a top-level "ltpc" — not the "ff"/"marketFF"
            # nesting that only 'full'/'full_d30' modes produce.
            ltpc = data.get("ltpc", {})
            ltp = ltpc.get("ltp")

            # These are index instruments; indices have no traded volume, and
            # ltpc mode carries no volume field at all. Report 0 rather than
            # inventing a number.
            volume = 0.0

            if ltp is None:
                return

            tick = Tick(
                instrument=instrument_key,
                price=float(ltp),
                volume=float(volume),
                timestamp=datetime.now(),
                is_trade=True
            )
            # Note: The protobuf decode by streamer usually outputs fields exactly as named in the proto
            await event_bus.publish("MARKET_TICK", tick)

        except Exception as e:
            logger.error(f"Error publishing tick: {e}")

    async def close(self):
        if self.streamer:
            self.streamer.disconnect()


# Module-level singleton — lives here (not main.py) so broker.py can import
# it without a circular import (main.py imports broker.py's router).
upstox_client = UpstoxV3Client(instrument_keys=list(INDEX_INSTRUMENT_KEYS.values()))
