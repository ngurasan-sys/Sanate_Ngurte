import logging
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)

OPTION_CHAIN_URL = "https://api.upstox.com/v2/option/chain"


class OptionChainLookupError(Exception):
    """Raised when the real option chain cannot be fetched from Upstox."""


async def fetch_option_chain(
    instrument_key: str,
    access_token: str,
    expiry_date: str = "current_week",
) -> List[Dict[str, Any]]:
    """Fetch the real put/call option chain for `instrument_key` (e.g.
    "NSE_INDEX|Nifty 50") via Upstox's actual documented endpoint
    (`GET /v2/option/chain`). One call returns every strike's real
    `oi`/`prev_oi`/`ltp`/`close_price`, plus `underlying_spot_price` — no
    separate spot feed or historical-OI persistence needed.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                OPTION_CHAIN_URL,
                params={
                    "instrument_key": instrument_key,
                    "expiry_date": expiry_date,
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "accept": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        raise OptionChainLookupError(f"Option chain request failed: {exc}")

    if response.status_code != 200:
        raise OptionChainLookupError(
            f"Option chain fetch failed ({response.status_code}): {response.text}"
        )

    data = response.json()
    chain = data.get("data", [])
    if not chain:
        raise OptionChainLookupError(
            f"Option chain response had no strikes for instrument_key={instrument_key!r}"
        )

    return chain
