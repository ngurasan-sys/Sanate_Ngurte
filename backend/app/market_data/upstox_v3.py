import asyncio
import logging
import json
import ssl
from typing import Dict, Any, Callable
from datetime import datetime

from upstox_client.api_client import ApiClient
from upstox_client.feeder.market_data_streamer_v3 import MarketDataStreamerV3

from .models import Tick
from backend.app.core.event_bus import event_bus

logger = logging.getLogger(__name__)

class UpstoxV3Client:
    def __init__(self, api_client: ApiClient = None, instrument_keys=None):
        self.api_client = api_client
        self.streamer = MarketDataStreamerV3(self.api_client, instrument_keys or []) if api_client else None
        self.subscriptions = set(instrument_keys) if instrument_keys else set()

        if self.streamer:
            self.streamer.on("message", self._on_message)
            self.streamer.on("open", self._on_open)
            self.streamer.on("close", self._on_close)
            self.streamer.on("error", self._on_error)

    async def connect(self):
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
        try:
            # Process protobuf decoded message (streamer library does this automatically)
            # The message format is a dictionary representing the protobuf schema
            # Assuming message contains feeds dictionary: { 'NSE_EQ|INE123': {'ff': {'marketFF': {'ltpc': {'ltp': 100}}}} }
            if "feeds" in message:
                for instrument_key, feed in message["feeds"].items():
                    asyncio.create_task(self._publish_tick(instrument_key, feed))
        except Exception as e:
            logger.error(f"Error processing V3 message: {e}")

    async def _publish_tick(self, instrument_key: str, data: dict):
        try:
            # Try to get data from Full Feed (ff) or Option Feed (of)
            ff = data.get("ff", {})
            marketFF = ff.get("marketFF", {})
            ltpc = marketFF.get("ltpc", {})

            # If full_d30 format
            ltp = ltpc.get("ltp")
            volume = marketFF.get("v", 0)

            if ltp is None:
                # Try finding LTP elsewhere in the dict if the schema is different
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
            self.streamer.close()
