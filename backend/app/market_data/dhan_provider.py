"""Dhan's MarketDataProvider implementation. Every method translates
Dhan's real API responses into the same canonical shapes Upstox's provider
already returns, so no strategy code changes. connect_feed()/disconnect_feed()
open and close Dhan's binary WebSocket feed, subscribing to the LTP ticker
packet for the platform's tracked indices (NIFTY/BANKNIFTY/SENSEX).
"""

import json
import logging
import struct
from datetime import date
from typing import Any, Dict, List, Optional

import httpx

from backend.app.core.dhan_instrument_master import dhan_instrument_master
from backend.app.core.event_bus import event_bus
from backend.app.market_data.market_quote import Quote
from backend.app.market_data.models import Tick

logger = logging.getLogger(__name__)

DHAN_BASE_URL = "https://api.dhan.co/v2"
DHAN_FEED_WS_URL = "wss://api-feed.dhan.co"
LTP_FEED_RESPONSE_CODE = 2


class DhanProviderError(Exception):
    """Raised when a real Dhan market-data request fails."""


def _headers(access_token: str) -> Dict[str, str]:
    return {"access-token": access_token, "Content-Type": "application/json", "Accept": "application/json"}


class DhanProvider:
    def __init__(self):
        self._ws = None
        self._running = False

    def instrument_key_for_index(self, underlying: str) -> str:
        return dhan_instrument_master.security_id_for_index(underlying)

    def _parse_packet(self, raw: bytes) -> Optional[Tick]:
        # Dhan's binary feed is little-endian (per DhanHQ v2 docs: "The data
        # on DhanHQ Websockets are sent in Little Endian"), NOT the network-
        # byte-order big-endian struct format you'd otherwise default to.
        if len(raw) < 16:
            return None
        code, _msg_len, _segment, security_id = struct.unpack("<BHBI", raw[:8])
        if code != LTP_FEED_RESPONSE_CODE:
            return None
        ltp, _trade_time = struct.unpack("<fI", raw[8:16])
        from datetime import datetime
        return Tick(instrument=str(security_id), price=float(ltp), volume=0.0, timestamp=datetime.now(), is_trade=True)

    def _parse_frame(self, raw: bytes) -> List[Tick]:
        """A single WebSocket binary frame from Dhan can multiplex several
        packets back-to-back (each with its own 8-byte header whose
        message_length tells you how far to advance for the next one).
        Walk the whole frame rather than only looking at the first packet,
        so ticks after the first in a frame aren't silently dropped."""
        ticks: List[Tick] = []
        offset = 0
        while offset + 8 <= len(raw):
            _code, msg_len, _segment, _security_id = struct.unpack("<BHBI", raw[offset:offset + 8])
            if msg_len <= 0:
                break
            packet = raw[offset:offset + msg_len]
            if len(packet) < msg_len:
                break
            tick = self._parse_packet(packet)
            if tick is not None:
                ticks.append(tick)
            offset += msg_len
        return ticks

    async def connect_feed(self) -> None:
        import websockets  # only imported here so the module stays importable without the dependency installed, matching upstox_v3.py's UPSTOX_AVAILABLE pattern

        from backend.app.core import dhan_auth
        token = dhan_auth.load_token()
        client_id = dhan_auth.load_client_id()
        if not token or not client_id:
            return

        url = f"{DHAN_FEED_WS_URL}?version=2&token={token}&clientId={client_id}&authType=2"
        self._ws = await websockets.connect(url)
        self._running = True

        instrument_list = []
        for underlying in ("NIFTY", "BANKNIFTY", "SENSEX"):
            try:
                security_id = dhan_instrument_master.security_id_for_index(underlying)
            except Exception:
                logger.warning("Could not resolve Dhan security_id for %s; skipping feed subscription for it.", underlying)
                continue
            instrument_list.append({"ExchangeSegment": "IDX_I", "SecurityId": str(security_id)})

        if instrument_list:
            subscribe_message = {
                "RequestCode": 15,  # Subscribe - Ticker Packet (Dhan feed request code annexure)
                "InstrumentCount": len(instrument_list),
                "InstrumentList": instrument_list,
            }
            await self._ws.send(json.dumps(subscribe_message))

        import asyncio
        asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                if not self._running:
                    break
                if isinstance(raw, str):
                    continue
                for tick in self._parse_frame(raw):
                    await event_bus.publish("MARKET_TICK", tick)
        except Exception:
            logger.exception("Dhan feed read loop terminated unexpectedly")

    async def disconnect_feed(self) -> None:
        self._running = False
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

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

        data = response.json().get("data", {})
        spot = data.get("last_price")
        oc = data.get("oc", {})
        rows = []
        for strike_str, legs in oc.items():
            strike = float(strike_str)
            row: Dict[str, Any] = {
                "strike_price": strike,
                "expiry": expiry_date,
                "underlying_spot_price": spot,
            }
            for leg_key, canonical_key in (("ce", "call_options"), ("pe", "put_options")):
                leg = legs.get(leg_key)
                if not leg:
                    continue
                option_type = "CE" if leg_key == "ce" else "PE"
                try:
                    underlying_name = _underlying_for_index_key(index_key)
                    security_id = dhan_instrument_master.security_id_for_option(
                        # index_key is Dhan's underlying security_id, not the underlying
                        # name — callers pass the underlying name separately via the
                        # instrument master's own state; this call resolves by strike
                        # under the assumption the master was loaded for this underlying.
                        underlying_name, expiry_date, strike, option_type,
                    )
                except Exception:
                    security_id = None
                    logger.warning(
                        "Dhan security_id resolution failed for underlying_index_key=%s "
                        "expiry=%s strike=%s option_type=%s; instrument_key will be None.",
                        index_key, expiry_date, strike, option_type,
                    )
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
        if not row:
            raise DhanProviderError(
                f"Dhan quote response contained no data for instrument_key={instrument_key!r}."
            )
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
