import logging
from datetime import date
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)

HISTORICAL_CANDLE_URL = "https://api.upstox.com/v2/historical-candle"


class HistoricalCandleLookupError(Exception):
    """Raised when real historical candle data cannot be fetched from Upstox."""


async def fetch_historical_candles(
    instrument_key: str,
    access_token: str,
    to_date: date,
    from_date: date,
    interval: str = "day",
) -> List[Dict[str, Any]]:
    """Fetch real daily OHLC candles for `instrument_key` (e.g.
    "NSE_INDEX|Nifty 50") via Upstox's actual documented endpoint
    (`GET /v2/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}`).

    `interval` valid values per Upstox's docs: "1minute", "30minute", "day",
    "week", "month" — NOT "daily" (a common typo/confusion in third-party
    summaries of this API).

    Returns oldest-to-newest (Upstox returns newest-first), each row:
    {"timestamp", "open", "high", "low", "close", "volume", "oi"}.
    """
    url = f"{HISTORICAL_CANDLE_URL}/{instrument_key}/{interval}/{to_date.isoformat()}/{from_date.isoformat()}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        raise HistoricalCandleLookupError(f"Historical candle request failed: {exc}")

    if response.status_code != 200:
        raise HistoricalCandleLookupError(
            f"Historical candle fetch failed ({response.status_code}): {response.text}"
        )

    data = response.json()
    candles = data.get("data", {}).get("candles", [])
    if not candles:
        raise HistoricalCandleLookupError(
            f"No historical candles returned for instrument_key={instrument_key!r} "
            f"between {from_date} and {to_date}"
        )

    rows = [
        {
            "timestamp": c[0],
            "open": c[1],
            "high": c[2],
            "low": c[3],
            "close": c[4],
            "volume": c[5],
            "oi": c[6],
        }
        for c in candles
    ]
    rows.reverse()  # Upstox returns newest-first; callers want chronological order
    return rows


def closes_from_candles(candles: List[Dict[str, Any]]) -> List[float]:
    """Extract the close-price series, chronological order, from
    fetch_historical_candles's row shape.
    """
    return [c["close"] for c in candles]
