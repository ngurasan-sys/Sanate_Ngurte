"""Dhan's MarketDataProvider implementation. Every method translates
Dhan's real API responses into the same canonical shapes Upstox's provider
already returns, so no strategy code changes. Feed connect/disconnect are
implemented in a follow-up task — calling them here raises, rather than
silently doing nothing.
"""

from datetime import date
from typing import Any, Dict, List

import httpx

from backend.app.core.dhan_instrument_master import dhan_instrument_master
from backend.app.market_data.market_quote import Quote

DHAN_BASE_URL = "https://api.dhan.co/v2"


class DhanProviderError(Exception):
    """Raised when a real Dhan market-data request fails."""


def _headers(access_token: str) -> Dict[str, str]:
    return {"access-token": access_token, "Content-Type": "application/json", "Accept": "application/json"}


class DhanProvider:
    def instrument_key_for_index(self, underlying: str) -> str:
        return dhan_instrument_master.security_id_for_index(underlying)

    async def connect_feed(self) -> None:
        raise NotImplementedError("Dhan live feed is implemented in a follow-up task.")

    async def disconnect_feed(self) -> None:
        raise NotImplementedError("Dhan live feed is implemented in a follow-up task.")

    async def fetch_option_chain(
        self, index_key: str, access_token: str, expiry_date: str = "current_week",
    ) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{DHAN_BASE_URL}/optionchain",
                    json={"UnderlyingScrip": int(index_key), "UnderlyingSeg": "IDX_I", "Expiry": expiry_date},
                    headers=_headers(access_token),
                )
        except httpx.HTTPError as exc:
            raise DhanProviderError(f"Dhan option chain request failed: {exc}")

        if response.status_code != 200:
            raise DhanProviderError(f"Dhan option chain fetch failed ({response.status_code}): {response.text}")

        oc = response.json().get("data", {}).get("oc", {})
        rows = []
        for strike_str, legs in oc.items():
            strike = float(strike_str)
            row: Dict[str, Any] = {"strike_price": strike}
            for leg_key, canonical_key in (("ce", "call_options"), ("pe", "put_options")):
                leg = legs.get(leg_key)
                if not leg:
                    continue
                option_type = "CE" if leg_key == "ce" else "PE"
                try:
                    security_id = dhan_instrument_master.security_id_for_option(
                        # index_key is Dhan's underlying security_id, not the underlying
                        # name — callers pass the underlying name separately via the
                        # instrument master's own state; this call resolves by strike
                        # under the assumption the master was loaded for this underlying.
                        _underlying_for_index_key(index_key), expiry_date, strike, option_type,
                    )
                except Exception:
                    security_id = None
                greeks = leg.get("greeks", {})
                row[canonical_key] = {
                    "instrument_key": security_id,
                    "market_data": {
                        "bid_price": leg.get("top_bid_price"),
                        "ask_price": leg.get("top_ask_price"),
                        "ltp": leg.get("last_price"),
                        "volume": leg.get("volume"),
                        "oi": leg.get("oi"),
                    },
                    "option_greeks": {
                        "iv": leg.get("implied_volatility"),
                        "delta": greeks.get("delta"),
                        "gamma": greeks.get("gamma"),
                        "theta": greeks.get("theta"),
                        "vega": greeks.get("vega"),
                    },
                }
            rows.append(row)
        return rows

    async def fetch_quote(self, instrument_key: str, access_token: str) -> Quote:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{DHAN_BASE_URL}/marketfeed/quote",
                    json={"NSE_FNO": [int(instrument_key)]},
                    headers=_headers(access_token),
                )
        except httpx.HTTPError as exc:
            raise DhanProviderError(f"Dhan quote request failed: {exc}")

        if response.status_code != 200:
            raise DhanProviderError(f"Dhan quote fetch failed ({response.status_code}): {response.text}")

        data = response.json().get("data", {})
        segment_data = next(iter(data.values()), {})
        row = segment_data.get(str(instrument_key)) or next(iter(segment_data.values()), {})
        depth = row.get("depth", {})
        buy = depth.get("buy") or []
        sell = depth.get("sell") or []
        return Quote(
            last_price=row.get("last_price", 0.0),
            bid=buy[0]["price"] if buy else None,
            ask=sell[0]["price"] if sell else None,
            volume=row.get("volume", 0),
        )

    async def fetch_historical_candles(
        self, instrument_key: str, access_token: str, to_date: date, from_date: date, interval: str = "day",
    ) -> List[Dict[str, Any]]:
        endpoint = "historical" if interval == "day" else "intraday"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{DHAN_BASE_URL}/charts/{endpoint}",
                    json={
                        "securityId": instrument_key, "exchangeSegment": "IDX_I", "instrument": "INDEX",
                        "fromDate": from_date.isoformat(), "toDate": to_date.isoformat(),
                    },
                    headers=_headers(access_token),
                )
        except httpx.HTTPError as exc:
            raise DhanProviderError(f"Dhan historical candle request failed: {exc}")

        if response.status_code != 200:
            raise DhanProviderError(f"Dhan historical candle fetch failed ({response.status_code}): {response.text}")

        body = response.json()
        rows = []
        for i in range(len(body.get("close", []))):
            rows.append({
                "timestamp": body["timestamp"][i], "open": body["open"][i], "high": body["high"][i],
                "low": body["low"][i], "close": body["close"][i], "volume": body["volume"][i], "oi": 0,
            })
        return rows


def _underlying_for_index_key(index_key: str) -> str:
    """Reverse-lookup: index_key is Dhan's numeric security_id for an
    underlying index; option-leg resolution needs the underlying's NAME
    (e.g. "NIFTY"), not its security_id. Delegates to the instrument
    master's own cached mapping rather than re-fetching anything."""
    for underlying in ("NIFTY", "BANKNIFTY", "SENSEX"):
        try:
            if dhan_instrument_master.security_id_for_index(underlying) == index_key:
                return underlying
        except Exception:
            continue
    raise DhanProviderError(f"Could not resolve underlying name for Dhan security_id {index_key!r}.")


dhan_provider = DhanProvider()
