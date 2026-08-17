"""Dhan's MarketDataProvider implementation. Every method translates
Dhan's real API responses into the same canonical shapes Upstox's provider
already returns, so no strategy code changes. connect_feed()/disconnect_feed()
open and close Dhan's binary WebSocket feed, subscribing to the LTP ticker
packet for the platform's tracked indices (NIFTY/BANKNIFTY/SENSEX).
"""

import asyncio
import json
import logging
import re
import struct
from datetime import date
from typing import Any, Dict, List, Optional

import httpx

from backend.app.core.dhan_instrument_master import dhan_instrument_master
from backend.app.core.event_bus import event_bus
from backend.app.market_data.market_quote import MarketQuoteLookupError, Quote
from backend.app.market_data.models import Tick
from backend.app.market_data.option_chain_client import OptionChainLookupError
from backend.app.market_data.symbols import INDEX_INSTRUMENT_KEYS

logger = logging.getLogger(__name__)

DHAN_BASE_URL = "https://api.dhan.co/v2"
DHAN_FEED_WS_URL = "wss://api-feed.dhan.co"
LTP_FEED_RESPONSE_CODE = 2

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Upstox's own query-parameter vocabulary, baked into MarketDataProvider's
# default argument and hardcoded in every strategy engine. Dhan's API only
# accepts a concrete YYYY-MM-DD expiry, so these are resolved against Dhan's
# /optionchain/expirylist (sorted ascending, nearest first) before use.
_RELATIVE_EXPIRY_INDEX = {"current_week": 0, "next_week": 1}


class DhanProviderError(OptionChainLookupError, MarketQuoteLookupError):
    """Raised when a real Dhan market-data request fails.

    Deliberately multiple-inherits from the Upstox-era lookup errors that
    existing strategy engines already catch by name, so a Dhan failure is
    degraded the same way an Upstox failure is (including triggering the
    documented current_week -> next_week fallbacks) without editing any
    strategy file.
    """


def _headers(access_token: str) -> Dict[str, str]:
    return {"access-token": access_token, "Content-Type": "application/json", "Accept": "application/json"}


class DhanProvider:
    def __init__(self):
        self._ws = None
        self._running = False
        self._read_task: Optional[asyncio.Task] = None

    def instrument_key_for_index(self, underlying: str) -> str:
        return dhan_instrument_master.security_id_for_index(underlying)

    # ---------------------- live feed ----------------------

    def _symbolic_instrument(self, security_id: int) -> str:
        """Translate Dhan's raw numeric security_id into the SAME symbolic
        instrument-key string Upstox's feed publishes (e.g. "NSE_INDEX|Nifty 50"),
        so Tick.instrument is genuinely broker-neutral and the substring/
        equality checks strategy engines already do against Upstox's format
        keep working under Dhan. Falls back to the raw id if unknown."""
        underlying = dhan_instrument_master.underlying_for_security_id(str(security_id))
        if underlying is None:
            return str(security_id)
        return INDEX_INSTRUMENT_KEYS.get(underlying, str(security_id))

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
        return Tick(
            instrument=self._symbolic_instrument(security_id),
            price=float(ltp), volume=0.0, timestamp=datetime.now(), is_trade=True,
        )

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

        # The instrument master is the only source of Dhan security_ids, and
        # nothing else loads it. Broker activation and app startup both route
        # through here, so this is the load point for the whole Dhan surface.
        await dhan_instrument_master.ensure_loaded()

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

        self._read_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                if not self._running:
                    break
                if isinstance(raw, str):
                    continue
                for tick in self._parse_frame(raw):
                    await event_bus.publish("MARKET_TICK", tick)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Dhan feed read loop terminated unexpectedly")

    async def disconnect_feed(self) -> None:
        self._running = False
        # Cancel the reader before closing the socket, otherwise a broker
        # switch leaves a dangling task that logs a spurious exception when
        # the socket it is iterating disappears underneath it.
        task, self._read_task = self._read_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    # ---------------------- option chain ----------------------

    async def _fetch_expiry_list(self, index_key: str, access_token: str) -> List[str]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{DHAN_BASE_URL}/optionchain/expirylist",
                    json={"UnderlyingScrip": int(index_key), "UnderlyingSeg": "IDX_I"},
                    headers=_headers(access_token),
                )
        except httpx.HTTPError as exc:
            raise DhanProviderError(f"Dhan expiry-list request failed: {exc}")

        if response.status_code != 200:
            raise DhanProviderError(
                f"Dhan expiry-list fetch failed ({response.status_code}): {response.text}"
            )
        expiries = response.json().get("data", []) or []
        if not expiries:
            raise DhanProviderError(
                f"Dhan returned no expiries for underlying security_id={index_key!r}."
            )
        return expiries

    async def _resolve_expiry_date(self, index_key: str, access_token: str, expiry_date: str) -> str:
        """Strategy code speaks Upstox's relative-expiry vocabulary
        ("current_week"/"next_week"); Dhan's API only accepts a concrete
        YYYY-MM-DD. Resolve via Dhan's own /optionchain/expirylist, which
        returns dates sorted ascending (nearest first)."""
        if _ISO_DATE_RE.match(expiry_date or ""):
            return expiry_date
        if expiry_date not in _RELATIVE_EXPIRY_INDEX:
            raise DhanProviderError(
                f"Unsupported expiry specifier {expiry_date!r} — expected YYYY-MM-DD, "
                f"'current_week' or 'next_week'."
            )
        index = _RELATIVE_EXPIRY_INDEX[expiry_date]
        expiries = await self._fetch_expiry_list(index_key, access_token)
        if index >= len(expiries):
            raise DhanProviderError(
                f"Dhan has no expiry at position {index} for {expiry_date!r} "
                f"(underlying security_id={index_key!r}, available={expiries})."
            )
        return expiries[index]

    async def fetch_option_chain(
        self, index_key: str, access_token: str, expiry_date: str = "current_week",
    ) -> List[Dict[str, Any]]:
        await dhan_instrument_master.ensure_loaded()
        resolved_expiry = await self._resolve_expiry_date(index_key, access_token, expiry_date)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{DHAN_BASE_URL}/optionchain",
                    json={"UnderlyingScrip": int(index_key), "UnderlyingSeg": "IDX_I", "Expiry": resolved_expiry},
                    headers=_headers(access_token),
                )
        except httpx.HTTPError as exc:
            raise DhanProviderError(f"Dhan option chain request failed: {exc}")

        if response.status_code != 200:
            raise DhanProviderError(f"Dhan option chain fetch failed ({response.status_code}): {response.text}")

        data = response.json().get("data", {})
        spot = data.get("last_price")
        oc = data.get("oc", {})
        if not oc:
            # Upstox's option_chain_client raises on an empty chain, and
            # several engines rely on catching that to trigger their
            # current_week -> next_week fallback. Returning [] here would
            # break the fallback and hand callers an empty list they then
            # index into.
            raise DhanProviderError(
                f"Dhan option chain response had no strikes for underlying "
                f"security_id={index_key!r} expiry={resolved_expiry!r}."
            )
        rows = []
        for strike_str, legs in oc.items():
            strike = float(strike_str)
            row: Dict[str, Any] = {
                "strike_price": strike,
                "expiry": resolved_expiry,
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
                        underlying_name, resolved_expiry, strike, option_type,
                    )
                except Exception:
                    security_id = None
                    logger.warning(
                        "Dhan security_id resolution failed for underlying_index_key=%s "
                        "expiry=%s strike=%s option_type=%s; instrument_key will be None.",
                        index_key, resolved_expiry, strike, option_type,
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

    # ---------------------- quotes / candles ----------------------

    def _segment_for_security_id(self, instrument_key: str) -> str:
        """SENSEX and its options live in BSE, not NSE — ask the instrument
        master for the real exchange instead of hardcoding NSE_FNO."""
        if dhan_instrument_master.is_index_security_id(instrument_key):
            return "IDX_I"
        exchange = dhan_instrument_master.exchange_for_security_id(instrument_key)
        return f"{exchange}_FNO" if exchange else "NSE_FNO"

    async def fetch_quote(self, instrument_key: str, access_token: str) -> Quote:
        segment = self._segment_for_security_id(instrument_key)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{DHAN_BASE_URL}/marketfeed/quote",
                    json={segment: [int(instrument_key)]},
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
    underlying = dhan_instrument_master.underlying_for_security_id(index_key)
    if underlying is not None:
        return underlying
    # Fallback for a master mocked at the older (id-only) API surface.
    for candidate in ("NIFTY", "BANKNIFTY", "SENSEX"):
        try:
            if dhan_instrument_master.security_id_for_index(candidate) == index_key:
                return candidate
        except Exception:
            continue
    raise DhanProviderError(f"Could not resolve underlying name for Dhan security_id {index_key!r}.")


dhan_provider = DhanProvider()
