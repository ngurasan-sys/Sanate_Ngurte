import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

FULL_QUOTE_URL = "https://api.upstox.com/v2/market-quote/quotes"


class MarketQuoteLookupError(Exception):
    """Raised when a real market quote cannot be fetched from Upstox."""


class Quote:
    def __init__(self, last_price: float, bid: Optional[float], ask: Optional[float], volume: int):
        self.last_price = last_price
        self.bid = bid
        self.ask = ask
        self.volume = volume


async def fetch_quote(instrument_key: str, access_token: str) -> Quote:
    """Fetch a real full market quote (LTP + best bid/ask + volume) via
    Upstox's actual documented endpoint (`GET /v2/market-quote/quotes`).

    Used for futures (no dedicated option-chain-style endpoint exists for
    a single instrument outside the option chain), where we need the
    executable bid/ask, not just LTP, to judge whether a price move is
    actually tradable.

    The response is keyed by an Upstox-internal compound key (not the
    instrument_key verbatim), so this takes the first entry back rather
    than assuming a specific key format — safe as long as exactly one
    instrument_key is requested per call, which is all this module does.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                FULL_QUOTE_URL,
                params={"instrument_key": instrument_key},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        raise MarketQuoteLookupError(f"Market quote request failed: {exc}")

    if response.status_code != 200:
        raise MarketQuoteLookupError(
            f"Market quote fetch failed ({response.status_code}): {response.text}"
        )

    body = response.json()
    data: Dict[str, Any] = body.get("data", {})
    if not data:
        raise MarketQuoteLookupError(f"No quote data returned for instrument_key={instrument_key!r}")

    row = next(iter(data.values()))
    depth = row.get("depth", {})
    buy = depth.get("buy") or []
    sell = depth.get("sell") or []

    return Quote(
        last_price=row.get("last_price", 0.0),
        bid=buy[0]["price"] if buy else None,
        ask=sell[0]["price"] if sell else None,
        volume=row.get("volume", 0),
    )
