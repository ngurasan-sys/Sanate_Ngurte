import logging
from datetime import date, datetime
from typing import Dict, Optional, Tuple

import httpx
import pytz

logger = logging.getLogger(__name__)

INSTRUMENT_SEARCH_URL = "https://api.upstox.com/v2/instruments/search"
IST = pytz.timezone("Asia/Kolkata")


class FuturesInstrumentLookupError(Exception):
    """Raised when the real current-month futures instrument_key cannot
    be resolved from Upstox."""


async def fetch_current_month_future_key(underlying: str, access_token: str) -> str:
    """Resolves the current-month index futures instrument_key for
    `underlying` (e.g. "NIFTY") via Upstox's real Instrument Search API
    (`GET /v2/instruments/search`, `instrument_types=FUT`,
    `expiry=current_month`) — index futures are monthly contracts, no
    weekly futures exist, unlike the weekly options chain.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                INSTRUMENT_SEARCH_URL,
                params={
                    "query": underlying,
                    "segments": "FO",
                    "instrument_types": "FUT",
                    "expiry": "current_month",
                    "records": 1,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "accept": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        raise FuturesInstrumentLookupError(f"Futures instrument search failed: {exc}")

    if response.status_code != 200:
        raise FuturesInstrumentLookupError(
            f"Futures instrument search failed ({response.status_code}): {response.text}"
        )

    data = response.json()
    items = data.get("data", [])
    if not items:
        raise FuturesInstrumentLookupError(f"No current-month future found for underlying={underlying!r}")

    instrument_key = items[0].get("instrument_key")
    if not instrument_key:
        raise FuturesInstrumentLookupError(
            f"Instrument search result missing instrument_key: {items[0]}"
        )
    return instrument_key


class FuturesInstrumentCache:
    """Caches the resolved current-month futures instrument_key per
    underlying, per IST calendar day — the contract doesn't change
    intraday, so there's no reason to re-resolve it more than once a day,
    same pattern as ExpiryCalendar.
    """

    def __init__(self):
        self._cache: Dict[str, Tuple[date, str]] = {}

    async def get(self, underlying: str, access_token: str) -> str:
        today = datetime.now(IST).date()
        cached = self._cache.get(underlying)
        if cached and cached[0] == today:
            return cached[1]

        instrument_key = await fetch_current_month_future_key(underlying, access_token)
        self._cache[underlying] = (today, instrument_key)
        return instrument_key


futures_instrument_cache = FuturesInstrumentCache()
