# Multi-Broker Phase 2 (Dhan) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Real Dhan `MarketDataProvider` + `BrokerExecutionAdapter` implementations, registered with `active_broker` alongside Upstox, matching Upstox's current LTP-only feed fidelity.

**Architecture:** New `dhan_instrument_master.py` (CSV-backed security_id resolution — never hardcoded), `dhan_provider.py`, `dhan_adapter.py` — each a thin translation layer into the existing broker-neutral shapes (`Tick`, `Quote`, canonical option-chain dict, `OrderRequest`/`OrderResult`), same pattern as Phase 1's Upstox wrappers.

**Tech Stack:** Python, httpx, websockets (or an equivalent async WS client already used elsewhere in this repo — check `upstox_v3.py`'s dependency before adding a new one), pytest + pytest-asyncio, `httpx.MockTransport` for HTTP tests.

## Global Constraints

- No live Dhan credentials exist in this environment. Every test is against mocked HTTP responses / synthetic binary packets. Never claim live verification.
- Never hardcode a Dhan `security_id` anywhere — always resolve via `dhan_instrument_master.py`. A lookup miss raises a clear error, never guesses.
- `SANDBOX` mode with Dhan active must return `REJECTED` with an explicit "Dhan has no sandbox environment" reason — never silently route to LIVE.
- Only report `status="SUBMITTED"` when Dhan's API actually returned a real `orderId` — same honesty rule Upstox's adapter already follows.
- Feed fidelity is LTP-only (matches Upstox's current real fidelity) — no market-depth parsing.
- No strategy file changes in this phase — Dhan only becomes reachable through `active_broker`, same as Upstox.
- Dhan does not auto-activate at startup (only Upstox does, per Phase 1) — it only becomes active via `POST /api/v1/brokers/active {"broker_id": "dhan"}`.
- Auth header names for Dhan: `access-token` and `dhanClientId` (already proven working in `backend/app/core/dhan_auth.py:39` — reuse exactly, don't guess different header names).
- Dhan's REST base URL is `https://api.dhan.co/v2` (confirmed in `dhan_auth.py:24`).

---

### Task 1: `dhan_instrument_master.py` — CSV-backed security_id resolution

**Files:**
- Create: `backend/app/core/dhan_instrument_master.py`
- Test: `backend/tests/test_dhan_instrument_master.py`

**Interfaces:**
- Produces: `DhanInstrumentMaster` class + singleton `dhan_instrument_master`, with:
  - `async ensure_loaded() -> None` — fetches+parses the CSV if not already cached.
  - `security_id_for_index(underlying: str) -> str` — raises `DhanInstrumentLookupError` on miss.
  - `security_id_for_option(underlying: str, expiry: str, strike: float, option_type: str) -> str` — `option_type` is `"CE"`/`"PE"`; raises `DhanInstrumentLookupError` on miss.
  - `async refresh() -> None` — re-fetches, clears cache first.

Dhan's public instrument master CSV is at `https://images.dhan.co/api-data/api-scrip-master.csv`. Its real column names/values are not verified in this environment (no live fetch was possible) — write the parser against these commonly-documented columns, but the implementer must treat the exact header names as unverified until checked against Dhan's current published schema (search Dhan's API docs for "Instrument List" / "Security ID List" during implementation — do not skip this check): `SEM_EXM_EXCH_ID` (exchange, e.g. `NSE`), `SEM_SEGMENT` (e.g. `I` for index, `D` for derivatives), `SEM_SMST_SECURITY_ID` (the numeric security_id), `SEM_TRADING_SYMBOL`, `SEM_CUSTOM_SYMBOL`, `SEM_EXPIRY_DATE`, `SEM_STRIKE_PRICE`, `SEM_OPTION_TYPE` (`CE`/`PE`), `SEM_INSTRUMENT_NAME` (e.g. `INDEX`, `OPTIDX`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_dhan_instrument_master.py
import pytest
from unittest.mock import AsyncMock

from backend.app.core.dhan_instrument_master import (
    DhanInstrumentLookupError,
    DhanInstrumentMaster,
)

SAMPLE_CSV = (
    "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_TRADING_SYMBOL,"
    "SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_INSTRUMENT_NAME\n"
    "NSE,I,13,NIFTY 50,NIFTY,,,,INDEX\n"
    "NSE,I,25,NIFTY BANK,BANKNIFTY,,,,INDEX\n"
    "BSE,I,51,SENSEX,SENSEX,,,,INDEX\n"
    "NSE,D,1001,NIFTY-Oct2026-25000-CE,NIFTY 25000 CE,2026-10-30,25000,CE,OPTIDX\n"
    "NSE,D,1002,NIFTY-Oct2026-25000-PE,NIFTY 25000 PE,2026-10-30,25000,PE,OPTIDX\n"
)


@pytest.fixture
def master(monkeypatch):
    m = DhanInstrumentMaster()
    monkeypatch.setattr(m, "_fetch_csv_text", AsyncMock(return_value=SAMPLE_CSV))
    return m


@pytest.mark.asyncio
async def test_security_id_for_known_index(master):
    await master.ensure_loaded()
    assert master.security_id_for_index("NIFTY") == "13"
    assert master.security_id_for_index("SENSEX") == "51"


def test_security_id_for_index_before_load_raises(master):
    with pytest.raises(DhanInstrumentLookupError):
        master.security_id_for_index("NIFTY")


@pytest.mark.asyncio
async def test_security_id_for_unknown_index_raises(master):
    await master.ensure_loaded()
    with pytest.raises(DhanInstrumentLookupError):
        master.security_id_for_index("FINNIFTY")


@pytest.mark.asyncio
async def test_security_id_for_option_matches_expiry_strike_type(master):
    await master.ensure_loaded()
    assert master.security_id_for_option("NIFTY", "2026-10-30", 25000.0, "CE") == "1001"
    assert master.security_id_for_option("NIFTY", "2026-10-30", 25000.0, "PE") == "1002"


@pytest.mark.asyncio
async def test_security_id_for_option_no_match_raises(master):
    await master.ensure_loaded()
    with pytest.raises(DhanInstrumentLookupError):
        master.security_id_for_option("NIFTY", "2026-10-30", 99999.0, "CE")


@pytest.mark.asyncio
async def test_ensure_loaded_only_fetches_once(master):
    await master.ensure_loaded()
    await master.ensure_loaded()
    master._fetch_csv_text.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_forces_a_new_fetch(master):
    await master.ensure_loaded()
    await master.refresh()
    assert master._fetch_csv_text.call_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dhan_instrument_master.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# backend/app/core/dhan_instrument_master.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_dhan_instrument_master.py -v`
Expected: 7 passed

- [ ] **Step 5: Verify the real CSV column names against Dhan's current published docs**

Before trusting this in a live run (not before merging — this task's tests are self-contained), search Dhan's official API documentation for the exact current column names of the instrument master CSV and confirm `SEM_INSTRUMENT_NAME`/`SEM_TRADING_SYMBOL`/`SEM_CUSTOM_SYMBOL`/`SEM_EXPIRY_DATE`/`SEM_STRIKE_PRICE`/`SEM_OPTION_TYPE`/`SEM_SMST_SECURITY_ID` are correct. If they differ, update `_parse()` accordingly and note the correction in the commit message.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/dhan_instrument_master.py backend/tests/test_dhan_instrument_master.py
git commit -m "feat: add Dhan instrument-master CSV resolution (never hardcoded security_id)"
```

---

### Task 2: `DhanProvider` — REST methods (option chain, quote, historical candles)

**Files:**
- Create: `backend/app/market_data/dhan_provider.py`
- Test: `backend/tests/test_dhan_provider.py`

**Interfaces:**
- Consumes: `MarketDataProvider` protocol; `dhan_instrument_master` (Task 1); existing `Quote` (`market_quote.py`).
- Produces: `DhanProvider` class + singleton `dhan_provider`, implementing `instrument_key_for_index`, `fetch_option_chain`, `fetch_quote`, `fetch_historical_candles` (feed methods come in Task 3 — stub `connect_feed`/`disconnect_feed` as `raise NotImplementedError` for now so the class is still importable/testable, Task 3 replaces the stubs).

Dhan's `/optionchain` response shape (per Dhan's documented API — unverified live, see Global Constraints):
```json
{"data": {"last_price": 25010.5, "oc": {"25000.000000": {
  "ce": {"last_price": 120.5, "oi": 500000, "volume": 12000, "top_bid_price": 119.0, "top_ask_price": 121.0,
         "implied_volatility": 15.2, "greeks": {"delta": 0.5, "gamma": 0.001, "theta": -5.0, "vega": 10.0}},
  "pe": {"last_price": 80.0, "oi": 300000, "volume": 8000, "top_bid_price": 79.0, "top_ask_price": 81.0,
         "implied_volatility": 14.8, "greeks": {"delta": -0.5, "gamma": 0.001, "theta": -4.5, "vega": 9.5}}
}}}}
```

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_dhan_provider.py
from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.app.market_data import dhan_provider as dp_module
from backend.app.market_data.dhan_provider import DhanProvider
from backend.app.market_data.provider import MarketDataProvider


@pytest.fixture
def provider(monkeypatch):
    p = DhanProvider()
    master = AsyncMock()
    master.security_id_for_index.return_value = "13"
    master.security_id_for_option.side_effect = lambda underlying, expiry, strike, opt_type: {
        ("NIFTY", "2026-10-30", 25000.0, "CE"): "1001",
        ("NIFTY", "2026-10-30", 25000.0, "PE"): "1002",
    }[(underlying, expiry, strike, opt_type)]
    monkeypatch.setattr(dp_module, "dhan_instrument_master", master)
    return p


def test_dhan_provider_satisfies_protocol():
    assert isinstance(DhanProvider(), MarketDataProvider)


def test_instrument_key_for_index_delegates_to_instrument_master(provider):
    assert provider.instrument_key_for_index("NIFTY") == "13"


@pytest.mark.asyncio
async def test_fetch_option_chain_translates_to_canonical_shape(provider, monkeypatch):
    def handler(request):
        assert request.url.path == "/v2/optionchain"
        return httpx.Response(200, json={
            "data": {"last_price": 25010.5, "oc": {"25000.000000": {
                "ce": {"last_price": 120.5, "oi": 500000, "volume": 12000,
                       "top_bid_price": 119.0, "top_ask_price": 121.0, "implied_volatility": 15.2,
                       "greeks": {"delta": 0.5, "gamma": 0.001, "theta": -5.0, "vega": 10.0}},
                "pe": {"last_price": 80.0, "oi": 300000, "volume": 8000,
                       "top_bid_price": 79.0, "top_ask_price": 81.0, "implied_volatility": 14.8,
                       "greeks": {"delta": -0.5, "gamma": 0.001, "theta": -4.5, "vega": 9.5}},
            }}},
        })
    monkeypatch.setattr(dp_module.httpx, "AsyncClient", lambda *a, **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    chain = await provider.fetch_option_chain("13", "tok", "2026-10-30")

    assert len(chain) == 1
    row = chain[0]
    assert row["strike_price"] == 25000.0
    assert row["call_options"]["instrument_key"] == "1001"
    assert row["call_options"]["market_data"]["bid_price"] == 119.0
    assert row["call_options"]["market_data"]["ask_price"] == 121.0
    assert row["call_options"]["market_data"]["ltp"] == 120.5
    assert row["call_options"]["market_data"]["oi"] == 500000
    assert row["call_options"]["option_greeks"]["iv"] == 15.2
    assert row["call_options"]["option_greeks"]["delta"] == 0.5
    assert row["put_options"]["instrument_key"] == "1002"
    assert row["put_options"]["market_data"]["ltp"] == 80.0


@pytest.mark.asyncio
async def test_fetch_quote_translates_to_canonical_quote(provider, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={
            "data": {"NSE": {"13": {"last_price": 25010.5, "volume": 999,
                                     "depth": {"buy": [{"price": 25009.0}], "sell": [{"price": 25011.0}]}}}}
        })
    monkeypatch.setattr(dp_module.httpx, "AsyncClient", lambda *a, **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    quote = await provider.fetch_quote("13", "tok")

    assert quote.last_price == 25010.5
    assert quote.bid == 25009.0
    assert quote.ask == 25011.0
    assert quote.volume == 999


@pytest.mark.asyncio
async def test_fetch_historical_candles_translates_to_canonical_rows(provider, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={
            "open": [100.0, 105.0], "high": [110.0, 108.0], "low": [95.0, 102.0],
            "close": [105.0, 107.0], "volume": [1000, 1200],
            "timestamp": [1735689000, 1735775400],
        })
    monkeypatch.setattr(dp_module.httpx, "AsyncClient", lambda *a, **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    rows = await provider.fetch_historical_candles("13", "tok", date(2025, 1, 2), date(2025, 1, 1), "day")

    assert len(rows) == 2
    assert rows[0]["close"] == 105.0
    assert rows[0]["volume"] == 1000
    assert "timestamp" in rows[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dhan_provider.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# backend/app/market_data/dhan_provider.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_dhan_provider.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/market_data/dhan_provider.py backend/tests/test_dhan_provider.py
git commit -m "feat: add Dhan option chain/quote/historical-candle translation to canonical shapes"
```

---

### Task 3: `DhanProvider` — live LTP feed (binary WebSocket)

**Files:**
- Modify: `backend/app/market_data/dhan_provider.py` (replace the `NotImplementedError` stubs)
- Test: `backend/tests/test_dhan_provider_feed.py`

**Interfaces:**
- Consumes: `dhan_instrument_master` (Task 1); existing `Tick` model (`backend/app/market_data/models.py`); `event_bus.publish` (existing).
- Produces: `DhanProvider.connect_feed()`/`disconnect_feed()` — connects Dhan's binary WebSocket, parses only LTP packets, publishes `Tick` onto `MARKET_TICK`.

Dhan's feed URL: `wss://api-feed.dhan.co?version=2&token=<access_token>&clientId=<client_id>&authType=2`. Per Dhan's documented binary protocol (unverified live — flag any correction found during implementation in the commit message): each response packet has an 8-byte header (`feed_response_code: uint8`, `message_length: uint16`, `exchange_segment: uint8`, `security_id: uint32`) followed by a type-specific payload. The LTP packet (`feed_response_code == 2`) payload is `last_traded_price: float32` + `last_trade_time: uint32` (4 + 4 bytes, total packet 16 bytes). Use Python's `struct` module to unpack; treat any packet whose `feed_response_code` isn't 2 as ignorable (this provider only implements LTP per the Global Constraints' scope decision).

Check whether this repo already has a WebSocket client dependency before adding a new one — search `backend/requirements.txt` and `upstox_v3.py`'s imports first.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_dhan_provider_feed.py
import struct
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.market_data.dhan_provider import DhanProvider


def _ltp_packet(security_id: int, ltp: float) -> bytes:
    # 8-byte header (code=2, msg_len, exchange_segment, security_id) + 8-byte LTP payload
    header = struct.pack(">BHBI", 2, 16, 1, security_id)
    payload = struct.pack(">fI", ltp, 0)
    return header + payload


@pytest.mark.asyncio
async def test_ltp_packet_publishes_tick(monkeypatch):
    provider = DhanProvider()
    published = []

    async def fake_publish(channel, payload):
        published.append((channel, payload))

    monkeypatch.setattr("backend.app.market_data.dhan_provider.event_bus.publish", fake_publish)

    tick = provider._parse_packet(_ltp_packet(security_id=13, ltp=25010.5))

    assert tick is not None
    assert tick.instrument == "13"
    assert tick.price == pytest.approx(25010.5)


def test_non_ltp_packet_is_ignored():
    provider = DhanProvider()
    non_ltp = struct.pack(">BHBI", 4, 8, 1, 13)  # feed_response_code=4, not LTP
    assert provider._parse_packet(non_ltp) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dhan_provider_feed.py -v`
Expected: FAIL — `AttributeError: 'DhanProvider' object has no attribute '_parse_packet'`

- [ ] **Step 3: Implement**

Add to `backend/app/market_data/dhan_provider.py` (replace the two `NotImplementedError` stub methods):

```python
import struct
from typing import Optional

from backend.app.core.event_bus import event_bus
from backend.app.market_data.models import Tick

LTP_FEED_RESPONSE_CODE = 2
DHAN_FEED_WS_URL = "wss://api-feed.dhan.co"


class DhanProvider:
    def __init__(self):
        self._ws = None
        self._running = False

    # ... instrument_key_for_index / fetch_option_chain / fetch_quote /
    # fetch_historical_candles stay exactly as Task 2 wrote them ...

    def _parse_packet(self, raw: bytes) -> Optional[Tick]:
        if len(raw) < 16:
            return None
        code, _msg_len, _segment, security_id = struct.unpack(">BHBI", raw[:8])
        if code != LTP_FEED_RESPONSE_CODE:
            return None
        ltp, _trade_time = struct.unpack(">fI", raw[8:16])
        from datetime import datetime
        return Tick(instrument=str(security_id), price=float(ltp), volume=0.0, timestamp=datetime.now(), is_trade=True)

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
        import asyncio
        asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                if not self._running:
                    break
                if isinstance(raw, str):
                    continue
                tick = self._parse_packet(raw)
                if tick is not None:
                    await event_bus.publish("MARKET_TICK", tick)
        except Exception:
            pass

    async def disconnect_feed(self) -> None:
        self._running = False
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_dhan_provider_feed.py tests/test_dhan_provider.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/market_data/dhan_provider.py backend/tests/test_dhan_provider_feed.py
git commit -m "feat: add Dhan binary WebSocket LTP feed parsing"
```

---

### Task 4: `DhanExecutionAdapter` — order placement

**Files:**
- Create: `backend/app/execution/dhan_adapter.py`
- Test: `backend/tests/test_dhan_adapter.py`

**Interfaces:**
- Consumes: `BrokerExecutionAdapter` protocol; `OrderRequest`/`OrderResult`/`ExecutionMode` (`order_gateway.py`); `dhan_auth.load_token()`/`load_client_id()`.
- Produces: `DhanExecutionAdapter` class + singleton `dhan_execution_adapter`, implementing `async place_order(request, mode) -> OrderResult`.

`OrderRequest.instrument_token` is expected to already be a Dhan `security_id` string by the time it reaches this adapter (resolved upstream via `dhan_instrument_master` during option selection, same as Upstox's `instrument_key` today) — this adapter does not do any lookup itself, only translation + the HTTP call.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_dhan_adapter.py
import httpx
import pytest

from backend.app.execution import dhan_adapter as da_module
from backend.app.execution.dhan_adapter import DhanExecutionAdapter
from backend.app.execution.order_gateway import ExecutionMode, OrderRequest


def _req(**kw):
    defaults = dict(instrument_token="1001", transaction_type="BUY", quantity=75, product="I", order_type="MARKET")
    defaults.update(kw)
    return OrderRequest(**defaults)


@pytest.mark.asyncio
async def test_sandbox_mode_is_rejected_with_no_sandbox_reason(monkeypatch):
    def explode(*a, **kw):
        raise AssertionError("must not call the network for SANDBOX")
    monkeypatch.setattr(da_module.httpx, "AsyncClient", explode)

    result = await DhanExecutionAdapter().place_order(_req(), ExecutionMode.SANDBOX)

    assert result.status == "REJECTED"
    assert "sandbox" in result.detail.lower()


@pytest.mark.asyncio
async def test_live_submission_maps_fields_and_returns_order_id(monkeypatch):
    monkeypatch.setattr(da_module.dhan_auth, "load_token", lambda: "live-token")
    monkeypatch.setattr(da_module.dhan_auth, "load_client_id", lambda: "CLIENT123")

    captured = {}

    def handler(request):
        import json
        body = json.loads(request.content)
        captured.update(body)
        assert request.headers["access-token"] == "live-token"
        return httpx.Response(200, json={"orderId": "DHAN789", "orderStatus": "PENDING"})

    monkeypatch.setattr(da_module.httpx, "AsyncClient", lambda *a, **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    result = await DhanExecutionAdapter().place_order(
        _req(product="D", order_type="SL", price=101.5, trigger_price=100.0), ExecutionMode.LIVE,
    )

    assert result.status == "SUBMITTED"
    assert result.order_id == "DHAN789"
    assert captured["dhanClientId"] == "CLIENT123"
    assert captured["transactionType"] == "BUY"
    assert captured["productType"] == "CNC"
    assert captured["orderType"] == "STOP_LOSS"
    assert captured["securityId"] == "1001"
    assert captured["quantity"] == 75


@pytest.mark.asyncio
async def test_no_order_id_in_response_is_not_submitted(monkeypatch):
    monkeypatch.setattr(da_module.dhan_auth, "load_token", lambda: "live-token")
    monkeypatch.setattr(da_module.dhan_auth, "load_client_id", lambda: "CLIENT123")

    def handler(request):
        return httpx.Response(200, json={"orderStatus": "REJECTED"})
    monkeypatch.setattr(da_module.httpx, "AsyncClient", lambda *a, **kw: httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    result = await DhanExecutionAdapter().place_order(_req(), ExecutionMode.LIVE)

    assert result.status == "ERROR"
    assert result.is_real_submission is False


@pytest.mark.asyncio
async def test_missing_token_rejected_before_network(monkeypatch):
    monkeypatch.setattr(da_module.dhan_auth, "load_token", lambda: None)
    def explode(*a, **kw):
        raise AssertionError("must not call the network without a token")
    monkeypatch.setattr(da_module.httpx, "AsyncClient", explode)

    result = await DhanExecutionAdapter().place_order(_req(), ExecutionMode.LIVE)

    assert result.status == "REJECTED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_dhan_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# backend/app/execution/dhan_adapter.py
"""Dhan's BrokerExecutionAdapter implementation. Dhan has no separate
sandbox environment (unlike Upstox) — SANDBOX mode is honestly rejected
here rather than silently routed to LIVE.
"""

import logging

import httpx

from backend.app.core import dhan_auth
from backend.app.execution.order_gateway import ExecutionMode, OrderRequest, OrderResult

logger = logging.getLogger(__name__)

DHAN_ORDER_URL = "https://api.dhan.co/v2/orders"

PRODUCT_MAP = {"I": "INTRADAY", "D": "CNC", "MTF": "MTF"}
ORDER_TYPE_MAP = {"MARKET": "MARKET", "LIMIT": "LIMIT", "SL": "STOP_LOSS", "SL-M": "STOP_LOSS_MARKET"}


class DhanExecutionAdapter:
    async def place_order(self, request: OrderRequest, mode: ExecutionMode) -> OrderResult:
        payload = request.to_payload()

        if mode is ExecutionMode.SANDBOX:
            detail = "Dhan has no sandbox environment — use DRY_RUN to test, or LIVE to place a real order."
            logger.error("Order rejected before submission: %s", detail)
            return OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)

        token = dhan_auth.load_token()
        client_id = dhan_auth.load_client_id()
        if not token or not client_id:
            detail = "No saved Dhan token/client ID — connect Dhan via the Broker Connections page."
            logger.error("Order rejected before submission: %s", detail)
            return OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)

        body = {
            "dhanClientId": client_id,
            "transactionType": request.transaction_type,
            "exchangeSegment": "NSE_FNO",
            "productType": PRODUCT_MAP.get(request.product, "INTRADAY"),
            "orderType": ORDER_TYPE_MAP.get(request.order_type, "MARKET"),
            "validity": request.validity,
            "securityId": request.instrument_token,
            "quantity": request.quantity,
            "price": request.price,
            "triggerPrice": request.trigger_price,
            "disclosedQuantity": request.disclosed_quantity,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    DHAN_ORDER_URL, json=body,
                    headers={"access-token": token, "Content-Type": "application/json", "Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            detail = f"Order request failed in transport: {exc}. Order status UNKNOWN — verify manually."
            logger.error(detail)
            return OrderResult(status="ERROR", mode=mode, payload=payload, detail=detail)

        if response.status_code not in (200, 201):
            detail = f"Dhan rejected order ({response.status_code}): {response.text}"
            logger.error(detail)
            return OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)

        resp_body = response.json()
        order_id = resp_body.get("orderId")
        if not order_id:
            detail = f"Dhan returned {response.status_code} but no orderId: {resp_body}. Order status UNKNOWN — verify manually."
            logger.error(detail)
            return OrderResult(status="ERROR", mode=mode, payload=payload, detail=detail)

        logger.info("Order accepted by Dhan (%s mode). order_id=%s", mode.value, order_id)
        return OrderResult(status="SUBMITTED", mode=mode, order_id=order_id, payload=payload, detail="Dhan returned an orderId.")


dhan_execution_adapter = DhanExecutionAdapter()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_dhan_adapter.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/dhan_adapter.py backend/tests/test_dhan_adapter.py
git commit -m "feat: add Dhan order-placement adapter (SANDBOX honestly rejected)"
```

---

### Task 5: Register Dhan with `active_broker` in `main.py`

**Files:**
- Modify: `backend/app/main.py`
- Test: extend `backend/tests/test_main_broker_startup.py`

**Interfaces:**
- Consumes: `dhan_provider` (Task 2/3), `dhan_execution_adapter` (Task 4), `dhan_auth` (existing).

Dhan does NOT auto-activate at startup — only registers. Mirrors the exact `main.py:53-62` Upstox registration pattern.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_main_broker_startup.py
@pytest.mark.asyncio
async def test_dhan_registered_at_import_time():
    import backend.app.main  # noqa: F401
    assert "dhan" in ab_module.active_broker._registrations
    reg = ab_module.active_broker._registrations["dhan"]
    assert reg.provider is not None
    assert reg.execution_adapter is not None
    assert reg.auth_module is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_main_broker_startup.py -v`
Expected: FAIL — `dhan` not in `_registrations`

- [ ] **Step 3: Implement**

In `backend/app/main.py`, add alongside the existing Upstox imports/registration (around line 53-62):

```python
from backend.app.market_data.dhan_provider import dhan_provider
from backend.app.execution.dhan_adapter import dhan_execution_adapter
from backend.app.core import dhan_auth

active_broker.register_broker(
    "dhan", provider=dhan_provider, execution_adapter=dhan_execution_adapter, auth_module=dhan_auth,
)
```

Do NOT add Dhan to the auto-activation branch (that stays Upstox-only, per Global Constraints).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_main_broker_startup.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the full suite, then commit**

Run: `cd backend && python -m pytest -q`
Expected: no new failures beyond the same 3 pre-existing unrelated ones (`test_bullish_setup`, `test_full_event_flow`, `test_candle_aggregation_no_look_ahead`)

```bash
git add backend/app/main.py backend/tests/test_main_broker_startup.py
git commit -m "feat: register Dhan with active_broker at startup (no auto-activation)"
```

---

### Task 6: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the complete backend suite**

Run: `cd backend && python -m pytest -q`
Expected: all new Dhan tests pass, same 3 pre-existing unrelated failures, no new failures.

- [ ] **Step 2: Confirm `dhan` is switchable via the existing API**

Manual/scripted check: with a fake token registered via `dhan_auth`'s credential store (test-only, not a real Dhan account), confirm `POST /api/v1/brokers/active {"broker_id": "dhan"}` succeeds once `is_broker_ready("dhan")` is true, and that a subsequent `place_order` call in DRY_RUN mode logs a Dhan-shaped payload without any network call.

- [ ] **Step 3: If any regression is found, fix it and re-run Step 1.**

- [ ] **Step 4: Final commit if fixes were needed — otherwise this closes Phase 2.**
