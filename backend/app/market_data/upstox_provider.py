"""Upstox's MarketDataProvider implementation — a pure wrapper around the
existing, already-working upstox_v3 / option_chain_client / market_quote /
historical_candles / symbols modules. No logic changes here; this only
gives Upstox's existing behavior a broker-agnostic front door so
active_broker.get_active_provider() can return it exactly like it will
Dhan's or Zerodha's provider in a later phase.
"""

import logging
from datetime import date
from typing import Any, Dict, List

from backend.app.core import upstox_auth

from .historical_candles import fetch_historical_candles
from .market_quote import fetch_quote
from .option_chain_client import fetch_option_chain
from .symbols import INDEX_INSTRUMENT_KEYS
from .upstox_v3 import upstox_client

logger = logging.getLogger(__name__)


class UpstoxProvider:
    def instrument_key_for_index(self, underlying: str) -> str:
        return INDEX_INSTRUMENT_KEYS[underlying]

    async def connect_feed(self) -> None:
        # configure() must run before connect() — upstox_client is built
        # with no api_client, so without configure() the streamer stays
        # None and connect() silently falls back to mock mode even with a
        # valid saved token. Load the token here (rather than relying on a
        # caller to have already configured it) so this works identically
        # whether reached from app startup or a future active-broker
        # switch.
        token = upstox_auth.load_token()
        if token:
            upstox_client.configure(token)
        else:
            logger.warning(
                "No saved Upstox token — connect_feed() will run in mock mode."
            )
        await upstox_client.connect()

    async def disconnect_feed(self) -> None:
        if hasattr(upstox_client, "close"):
            await upstox_client.close()

    async def fetch_option_chain(
        self, index_key: str, access_token: str, expiry_date: str = "current_week",
    ) -> List[Dict[str, Any]]:
        return await fetch_option_chain(index_key, access_token, expiry_date)

    async def fetch_quote(self, instrument_key: str, access_token: str):
        return await fetch_quote(instrument_key, access_token)

    async def fetch_historical_candles(
        self, instrument_key: str, access_token: str, to_date: date, from_date: date,
        interval: str = "day",
    ) -> List[Dict[str, Any]]:
        return await fetch_historical_candles(instrument_key, access_token, to_date, from_date, interval)


upstox_provider = UpstoxProvider()
