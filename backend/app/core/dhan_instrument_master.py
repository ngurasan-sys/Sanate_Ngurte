"""Dhan security_id resolution — CSV-backed, never hardcoded. Dhan has no
live instrument-search API (unlike Upstox); the only source of truth is
its public instrument-master CSV. A lookup miss raises rather than
guessing, since a wrong security_id silently misroutes a real order.
"""

import csv
import io
import logging
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

INSTRUMENT_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

INDEX_TRADING_SYMBOLS = {
    "NIFTY": "NIFTY 50",
    "BANKNIFTY": "NIFTY BANK",
    "SENSEX": "SENSEX",
}


class DhanInstrumentLookupError(Exception):
    """Raised when a security_id can't be resolved — never guessed."""


class DhanInstrumentMaster:
    def __init__(self):
        self._index_ids: Dict[str, str] = {}
        self._option_ids: Dict[tuple, str] = {}  # (underlying, expiry, strike, option_type) -> security_id
        self._loaded = False

    async def _fetch_csv_text(self) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(INSTRUMENT_MASTER_URL)
        response.raise_for_status()
        return response.text

    def _parse(self, csv_text: str) -> None:
        self._index_ids = {}
        self._option_ids = {}
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            instrument = row.get("SEM_INSTRUMENT_NAME", "")
            security_id = row.get("SEM_SMST_SECURITY_ID", "")
            if instrument == "INDEX":
                trading_symbol = row.get("SEM_TRADING_SYMBOL", "")
                for underlying, symbol in INDEX_TRADING_SYMBOLS.items():
                    if trading_symbol == symbol:
                        self._index_ids[underlying] = security_id
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
                        self._option_ids[(underlying, expiry, strike, option_type)] = security_id
                        break

    async def ensure_loaded(self) -> None:
        if self._loaded:
            return
        text = await self._fetch_csv_text()
        self._parse(text)
        self._loaded = True

    async def refresh(self) -> None:
        self._loaded = False
        await self.ensure_loaded()

    def security_id_for_index(self, underlying: str) -> str:
        if not self._loaded:
            raise DhanInstrumentLookupError("Instrument master not loaded — call ensure_loaded() first.")
        security_id = self._index_ids.get(underlying)
        if security_id is None:
            raise DhanInstrumentLookupError(f"No Dhan security_id found for index {underlying!r}.")
        return security_id

    def security_id_for_option(self, underlying: str, expiry: str, strike: float, option_type: str) -> str:
        if not self._loaded:
            raise DhanInstrumentLookupError("Instrument master not loaded — call ensure_loaded() first.")
        security_id = self._option_ids.get((underlying, expiry, strike, option_type))
        if security_id is None:
            raise DhanInstrumentLookupError(
                f"No Dhan security_id found for {underlying} {expiry} {strike} {option_type}."
            )
        return security_id


dhan_instrument_master = DhanInstrumentMaster()
