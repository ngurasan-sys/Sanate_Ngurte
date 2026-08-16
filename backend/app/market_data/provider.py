"""Broker-agnostic market data interface every broker's data client
implements — Upstox today, Dhan/Zerodha in later phases. Strategy code
never imports a specific broker's market-data module directly; it goes
through backend.app.core.active_broker.get_active_provider() instead, so
switching the active broker changes where data comes from without any
strategy code changing.
"""

from datetime import date
from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class MarketDataProvider(Protocol):
    def instrument_key_for_index(self, underlying: str) -> str:
        """Map a logical underlying name ("NIFTY", "SENSEX", "BANKNIFTY")
        to this broker's native instrument key for that index."""
        ...

    async def connect_feed(self) -> None:
        """Start streaming live ticks, publishing the broker-neutral Tick
        model (backend.app.market_data.models.Tick) onto the MARKET_TICK
        event-bus channel."""
        ...

    async def disconnect_feed(self) -> None:
        """Stop the live tick stream started by connect_feed()."""
        ...

    async def fetch_option_chain(
        self, index_key: str, access_token: str, expiry_date: str = "current_week",
    ) -> List[Dict[str, Any]]:
        """Fetch the real option chain for index_key. Returns the
        canonical shape every strategy already parses: a list of
        per-strike dicts, each with call_options/put_options, each of
        those with market_data (bid_price/ask_price/ltp/volume/oi) and
        option_greeks (iv/delta/gamma/theta/vega)."""
        ...

    async def fetch_quote(self, instrument_key: str, access_token: str):
        """Fetch a single-instrument quote (LTP + best bid/ask + volume).
        Returns backend.app.market_data.market_quote.Quote."""
        ...

    async def fetch_historical_candles(
        self, instrument_key: str, access_token: str, to_date: date, from_date: date,
        interval: str = "day",
    ) -> List[Dict[str, Any]]:
        """Fetch historical OHLC candles. Returns the canonical row shape
        {"timestamp","open","high","low","close","volume","oi"}, oldest
        first."""
        ...
