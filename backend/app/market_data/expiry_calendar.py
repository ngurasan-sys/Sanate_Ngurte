import logging
from datetime import date, datetime
from typing import Dict, Optional, Tuple

import httpx
import pytz

logger = logging.getLogger(__name__)

INSTRUMENT_SEARCH_URL = "https://api.upstox.com/v2/instruments/search"
IST = pytz.timezone("Asia/Kolkata")


class ExpiryLookupError(Exception):
    """Raised when the real expiry date cannot be resolved from Upstox."""


async def fetch_current_week_expiry(
    query: str,
    access_token: str,
    segments: str = "FO",
    instrument_types: str = "FUT",
) -> date:
    """Resolve the nearest (current-week) expiry date for `query` (e.g.
    "NIFTY") via Upstox's real Instrument Search API — the actual documented
    endpoint (`GET /v2/instruments/search`, `expiry=current_week`), not a
    hardcoded weekly-expiry-day-of-week assumption. NSE's weekly expiry day
    has changed across contracts/years, so a real lookup is the only honest
    way to know today's expiry status.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                INSTRUMENT_SEARCH_URL,
                params={
                    "query": query,
                    "segments": segments,
                    "instrument_types": instrument_types,
                    "expiry": "current_week",
                    "records": 1,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "accept": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        raise ExpiryLookupError(f"Instrument search request failed: {exc}")

    if response.status_code != 200:
        raise ExpiryLookupError(
            f"Instrument search failed ({response.status_code}): {response.text}"
        )

    data = response.json()
    items = data.get("data", [])
    if not items:
        raise ExpiryLookupError(f"No instruments found for query={query!r}")

    expiry_str = items[0].get("expiry")
    if not expiry_str:
        raise ExpiryLookupError(
            f"Instrument search result missing expiry field: {items[0]}"
        )

    return date.fromisoformat(expiry_str)


class ExpiryCalendar:
    """Caches the resolved current-week expiry date per (symbol, segments,
    instrument_types) key, per IST calendar day — expiry doesn't change
    intraday, so there is no reason to call the real API more than once a
    day per symbol.
    """

    def __init__(self):
        # key -> (resolved_on_day, expiry_date)
        self._cache: Dict[Tuple[str, str, str], Tuple[date, date]] = {}

    async def is_today_expiry_day(
        self,
        symbol: str,
        access_token: str,
        segments: str = "FO",
        instrument_types: str = "FUT",
    ) -> bool:
        today = datetime.now(IST).date()
        key = (symbol, segments, instrument_types)
        cached = self._cache.get(key)
        if cached and cached[0] == today:
            return cached[1] == today

        expiry = await fetch_current_week_expiry(
            symbol, access_token, segments, instrument_types
        )
        self._cache[key] = (today, expiry)
        return expiry == today

    def cached_expiry(self, symbol: str, segments: str = "FO", instrument_types: str = "FUT") -> Optional[date]:
        cached = self._cache.get((symbol, segments, instrument_types))
        return cached[1] if cached else None


expiry_calendar = ExpiryCalendar()
