"""Dhan security_id resolution — CSV-backed, never hardcoded. Dhan has no
live instrument-search API (unlike Upstox); the only source of truth is
its public instrument-master CSV. A lookup miss raises rather than
guessing, since a wrong security_id silently misroutes a real order.
"""

import asyncio
import csv
import io
import logging
from typing import Dict, Optional

import httpx

from backend.app.market_data.option_chain_client import OptionChainLookupError

logger = logging.getLogger(__name__)

INSTRUMENT_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

# ensure_loaded() is on the critical path of connect_feed()/fetch_option_chain()
# now, so an unresponsive CDN must not hang broker activation forever.
CSV_FETCH_TIMEOUT_SECONDS = 30.0

INDEX_TRADING_SYMBOLS = {
    "NIFTY": "NIFTY 50",
    "BANKNIFTY": "NIFTY BANK",
    "SENSEX": "SENSEX",
}


class DhanInstrumentLookupError(KeyError, OptionChainLookupError):
    """Raised when a security_id can't be resolved — never guessed.

    Deliberately multiple-inherits from the exception types existing
    (Upstox-shaped) strategy code already catches: `except KeyError`
    around instrument_key_for_index(), and `except OptionChainLookupError`
    around chain fetches. Without this, a Dhan lookup miss would escape
    poll loops as an unhandled exception instead of being degraded the
    same way an Upstox miss already is.
    """

    def __str__(self) -> str:  # KeyError's __str__ is repr(args[0]) — undo that
        return ", ".join(str(a) for a in self.args)


class DhanInstrumentMaster:
    def __init__(self):
        self._index_ids: Dict[str, str] = {}
        self._option_ids: Dict[tuple, str] = {}  # (underlying, expiry, strike, option_type) -> security_id
        self._index_exchanges: Dict[str, str] = {}  # underlying -> "NSE"/"BSE"
        self._option_exchanges: Dict[tuple, str] = {}
        self._exchange_by_security_id: Dict[str, str] = {}
        self._underlying_by_index_id: Dict[str, str] = {}
        self._loaded = False
        self._load_lock = asyncio.Lock()

    async def _fetch_csv_text(self) -> str:
        async with httpx.AsyncClient(timeout=CSV_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(INSTRUMENT_MASTER_URL)
        response.raise_for_status()
        return response.text

    def _parse(self, csv_text: str) -> None:
        self._index_ids = {}
        self._option_ids = {}
        self._index_exchanges = {}
        self._option_exchanges = {}
        self._exchange_by_security_id = {}
        self._underlying_by_index_id = {}
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            instrument = row.get("SEM_INSTRUMENT_NAME", "")
            security_id = row.get("SEM_SMST_SECURITY_ID", "")
            exchange = (row.get("SEM_EXM_EXCH_ID", "") or "").strip().upper()
            if instrument == "INDEX":
                trading_symbol = row.get("SEM_TRADING_SYMBOL", "")
                for underlying, symbol in INDEX_TRADING_SYMBOLS.items():
                    if trading_symbol == symbol:
                        self._index_ids[underlying] = security_id
                        self._index_exchanges[underlying] = exchange
                        self._exchange_by_security_id[str(security_id)] = exchange
                        self._underlying_by_index_id[str(security_id)] = underlying
            elif instrument == "OPTIDX":
                custom = row.get("SEM_CUSTOM_SYMBOL", "")
                option_type = row.get("SEM_OPTION_TYPE", "")
                expiry = row.get("SEM_EXPIRY_DATE", "")
                strike_raw = row.get("SEM_STRIKE_PRICE", "")
                try:
                    strike = float(strike_raw)
                except ValueError:
                    continue
                for underlying in INDEX_TRADING_SYMBOLS:
                    if custom.startswith(underlying):
                        key = (underlying, expiry, strike, option_type)
                        self._option_ids[key] = security_id
                        self._option_exchanges[key] = exchange
                        self._exchange_by_security_id[str(security_id)] = exchange
                        break

    async def ensure_loaded(self) -> None:
        if self._loaded:
            return
        # Double-checked locking: connect_feed() and concurrent strategy
        # fetch_option_chain() calls all reach here, and the CSV is a
        # multi-megabyte download — only one caller should fetch it.
        async with self._load_lock:
            if self._loaded:
                return
            text = await self._fetch_csv_text()
            self._parse(text)
            self._loaded = True
            logger.info(
                "Dhan instrument master loaded: %d indices, %d index options.",
                len(self._index_ids), len(self._option_ids),
            )

    async def refresh(self) -> None:
        self._loaded = False
        await self.ensure_loaded()

    # ---------------------- lookups ----------------------

    def security_id_for_index(self, underlying: str) -> str:
        self._require_loaded()
        security_id = self._index_ids.get(underlying)
        if security_id is None:
            raise DhanInstrumentLookupError(f"No Dhan security_id found for index {underlying!r}.")
        return security_id

    def security_id_for_option(self, underlying: str, expiry: str, strike: float, option_type: str) -> str:
        self._require_loaded()
        security_id = self._option_ids.get((underlying, expiry, strike, option_type))
        if security_id is None:
            raise DhanInstrumentLookupError(
                f"No Dhan security_id found for {underlying} {expiry} {strike} {option_type}."
            )
        return security_id

    def exchange_for_index(self, underlying: str) -> str:
        """"NSE"/"BSE" for an index — SENSEX is BSE, so the caller can build
        the right BSE_FNO/NSE_FNO segment instead of hardcoding NSE."""
        self._require_loaded()
        exchange = self._index_exchanges.get(underlying)
        if not exchange:
            raise DhanInstrumentLookupError(f"No Dhan exchange found for index {underlying!r}.")
        return exchange

    def exchange_for_option(self, underlying: str, expiry: str, strike: float, option_type: str) -> str:
        self._require_loaded()
        exchange = self._option_exchanges.get((underlying, expiry, strike, option_type))
        if not exchange:
            raise DhanInstrumentLookupError(
                f"No Dhan exchange found for {underlying} {expiry} {strike} {option_type}."
            )
        return exchange

    def exchange_for_security_id(self, security_id: str) -> Optional[str]:
        """Best-effort reverse lookup used by order placement / quote
        fetching, where all the caller holds is the numeric security_id.
        Returns None (rather than raising) when unknown or not yet
        loaded, so callers can fall back to their previous default."""
        if not self._loaded:
            return None
        return self._exchange_by_security_id.get(str(security_id))

    def underlying_for_security_id(self, security_id: str) -> Optional[str]:
        """Reverse map an INDEX security_id ("13") to its underlying name
        ("NIFTY"). Returns None when unknown or not yet loaded."""
        if not self._loaded:
            return None
        return self._underlying_by_index_id.get(str(security_id))

    def is_index_security_id(self, security_id: str) -> bool:
        return self.underlying_for_security_id(security_id) is not None

    def _require_loaded(self) -> None:
        if not self._loaded:
            raise DhanInstrumentLookupError(
                "Instrument master not loaded — call ensure_loaded() first."
            )


dhan_instrument_master = DhanInstrumentMaster()
