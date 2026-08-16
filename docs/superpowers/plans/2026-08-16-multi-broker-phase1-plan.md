# Multi-Broker Support — Phase 1 (Provider/Adapter Interfaces) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the platform broker-agnostic for both live market data and order execution, with Upstox refactored onto the new interfaces with **zero behavior change**, so Phase 2 (Dhan) and Phase 3 (Zerodha) can each plug in without touching strategy code.

**Architecture:** Two `Protocol` interfaces — `MarketDataProvider` (tick feed, option chain, quote, historical candles, instrument-key mapping) and `BrokerExecutionAdapter` (`place_order`) — plus a persisted "active broker" switch (`backend/app/core/active_broker.py`) that every strategy/execution call site resolves at the point of use instead of importing a specific broker's module. Upstox's existing logic is wrapped, not rewritten, behind both interfaces.

**Tech Stack:** Python 3.12/3.14, FastAPI, pytest + pytest-asyncio, httpx (mocked via `httpx.MockTransport` in tests), React/TypeScript frontend.

## Global Constraints

- Zero behavior change for Upstox-only usage: with Upstox as the only connected+active broker, every code path must behave exactly as it does today. This is the primary acceptance test for this phase.
- The full existing backend test suite must stay green: 885 passed, 3 pre-existing unrelated failures (`test_bullish_setup`, `test_full_event_flow`, `test_candle_aggregation_no_look_ahead`) — same 3, no new failures, no new passes expected to flip.
- The two-factor LIVE arm switch (`resolve_mode()` in `order_gateway.py`, plus the runtime arm switch in `execution/runtime_state.py`) keeps its exact safety semantics. Only its env var *names* become broker-neutral (`EXECUTION_MODE` / `LIVE_TRADING_CONFIRMED`, confirmed with the user — not per-broker).
- DRY_RUN mode never touches the active-broker machinery — it is handled entirely inside `order_gateway.py` before any adapter is resolved, exactly as today. Only SANDBOX/LIVE modes require an active, ready broker.
- No strategy file's *logic* changes in this phase — only the import of a specific Upstox module is redirected to `active_broker.get_active_provider()` / `get_active_execution_adapter()` / `get_active_auth_module()`.
- Never silently fall back to a default broker. If no broker is active, market-data-dependent strategies simply get no ticks, and order placement returns `REJECTED` with an explicit "no active broker" reason.
- Switching the active broker is blocked while any strategy with its own position tracking (CAS Dislocation, Manual Trading, OFAO) has an open position — reported with which strategy/position is blocking.
- This phase does **not** add Dhan or Zerodha data/execution logic — those are Phase 2 and Phase 3, each with their own plan.

---

## File Structure

New files:
- `backend/app/market_data/provider.py` — `MarketDataProvider` protocol.
- `backend/app/market_data/upstox_provider.py` — Upstox's `MarketDataProvider` implementation (wraps existing modules).
- `backend/app/execution/broker_adapter.py` — `BrokerExecutionAdapter` protocol.
- `backend/app/execution/upstox_adapter.py` — Upstox's `BrokerExecutionAdapter` implementation (the SANDBOX/LIVE network-call logic moved out of `order_gateway.py`, unchanged in substance).
- `backend/app/core/active_broker.py` — the active-broker registry/switch.
- Tests: `backend/tests/test_broker_provider_protocols.py`, `backend/tests/test_active_broker.py`, `backend/tests/test_upstox_provider.py`, `backend/tests/test_main_broker_startup.py`.

Modified files (see each task for exact diffs):
- `backend/app/execution/order_gateway.py` — becomes a thin DRY_RUN/dispatch layer.
- `backend/app/api/endpoints/execution_control.py`, `backend/app/engines/risk.py`, `backend/app/execution/runtime_state.py`, `backend/app/strategies/manual_trading/engine.py`, `backend/.env.example`, `frontend/src/views/ExecutionControlView.tsx` — env var rename.
- `backend/app/strategies/cas_dislocation/engine.py`, `backend/app/strategies/manual_trading/engine.py` (adds `get_open_position_blocker`), `backend/app/strategies/order_flow_absorption/state_machine.py` + `engine.py` (adds open-position query).
- `backend/app/main.py` — startup/shutdown wiring.
- `backend/app/strategies/cas_dislocation/engine.py`, `backend/app/strategies/expiry_engine.py`, `backend/app/strategies/expiry_reversal/engine.py`, `backend/app/strategies/manual_trading/engine.py`, `backend/app/strategies/option_analytics/engine.py`, `backend/app/strategies/order_flow_absorption/engine.py` — call-site migration.
- `backend/app/api/endpoints/brokers.py` — `GET`/`POST /api/v1/brokers/active`.
- `backend/app/api/endpoints/broker.py` — drop the direct feed-connect call from the legacy Upstox-only callback.
- `frontend/src/views/BrokerConnectionsView.tsx` — "Make Active" action + active-broker indicator.

---

### Task 1: Broker-agnostic provider/adapter protocols

**Files:**
- Create: `backend/app/market_data/provider.py`
- Create: `backend/app/execution/broker_adapter.py`
- Test: `backend/tests/test_broker_provider_protocols.py`

**Interfaces:**
- Produces: `MarketDataProvider` (runtime-checkable `Protocol`) with `instrument_key_for_index(underlying: str) -> str`, `async connect_feed() -> None`, `async disconnect_feed() -> None`, `async fetch_option_chain(index_key: str, access_token: str, expiry_date: str = "current_week") -> List[Dict[str, Any]]`, `async fetch_quote(instrument_key: str, access_token: str)`, `async fetch_historical_candles(instrument_key: str, access_token: str, to_date: date, from_date: date, interval: str = "day") -> List[Dict[str, Any]]`.
- Produces: `BrokerExecutionAdapter` (runtime-checkable `Protocol`) with `async place_order(request: OrderRequest, mode: ExecutionMode) -> OrderResult`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_broker_provider_protocols.py
from backend.app.execution.broker_adapter import BrokerExecutionAdapter
from backend.app.market_data.provider import MarketDataProvider


class _FakeProvider:
    def instrument_key_for_index(self, underlying):
        return f"FAKE|{underlying}"

    async def connect_feed(self):
        pass

    async def disconnect_feed(self):
        pass

    async def fetch_option_chain(self, index_key, access_token, expiry_date="current_week"):
        return []

    async def fetch_quote(self, instrument_key, access_token):
        return None

    async def fetch_historical_candles(self, instrument_key, access_token, to_date, from_date, interval="day"):
        return []


class _IncompleteProvider:
    def instrument_key_for_index(self, underlying):
        return underlying


class _FakeAdapter:
    async def place_order(self, request, mode):
        return None


class _IncompleteAdapter:
    pass


def test_fake_provider_satisfies_protocol():
    assert isinstance(_FakeProvider(), MarketDataProvider)


def test_incomplete_provider_does_not_satisfy_protocol():
    assert not isinstance(_IncompleteProvider(), MarketDataProvider)


def test_fake_adapter_satisfies_protocol():
    assert isinstance(_FakeAdapter(), BrokerExecutionAdapter)


def test_incomplete_adapter_does_not_satisfy_protocol():
    assert not isinstance(_IncompleteAdapter(), BrokerExecutionAdapter)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_broker_provider_protocols.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.market_data.provider'`

- [ ] **Step 3: Create the protocol files**

```python
# backend/app/market_data/provider.py
"""Broker-agnostic market data interface every broker's data client
implements — Upstox today, Dhan/Zerodha in later phases. Strategy code
never imports a specific broker's market-data module directly; it goes
through backend.app.core.active_broker.get_active_provider() instead, so
switching the active broker changes where data comes from without any
strategy code changing.
"""

from datetime import date
from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class MarketDataProvider(Protocol):
    def instrument_key_for_index(self, underlying: str) -> str:
        """Map a logical underlying name ("NIFTY", "SENSEX", "BANKNIFTY")
        to this broker's native instrument key for that index."""
        ...

    async def connect_feed(self) -> None:
        """Start streaming live ticks, publishing the broker-neutral Tick
        model (backend.app.market_data.models.Tick) onto the MARKET_TICK
        event-bus channel."""
        ...

    async def disconnect_feed(self) -> None:
        """Stop the live tick stream started by connect_feed()."""
        ...

    async def fetch_option_chain(
        self, index_key: str, access_token: str, expiry_date: str = "current_week",
    ) -> List[Dict[str, Any]]:
        """Fetch the real option chain for index_key. Returns the
        canonical shape every strategy already parses: a list of
        per-strike dicts, each with call_options/put_options, each of
        those with market_data (bid_price/ask_price/ltp/volume/oi) and
        option_greeks (iv/delta/gamma/theta/vega)."""
        ...

    async def fetch_quote(self, instrument_key: str, access_token: str):
        """Fetch a single-instrument quote (LTP + best bid/ask + volume).
        Returns backend.app.market_data.market_quote.Quote."""
        ...

    async def fetch_historical_candles(
        self, instrument_key: str, access_token: str, to_date: date, from_date: date,
        interval: str = "day",
    ) -> List[Dict[str, Any]]:
        """Fetch historical OHLC candles. Returns the canonical row shape
        {"timestamp","open","high","low","close","volume","oi"}, oldest
        first."""
        ...
```

```python
# backend/app/execution/broker_adapter.py
"""Broker-agnostic order-execution interface every broker's execution
client implements — Upstox today, Dhan/Zerodha in later phases.
order_gateway.OrderGateway dispatches to whichever broker is active via
backend.app.core.active_broker.get_active_execution_adapter(); it never
imports a specific broker's execution module directly.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from backend.app.execution.order_gateway import ExecutionMode, OrderRequest, OrderResult


@runtime_checkable
class BrokerExecutionAdapter(Protocol):
    async def place_order(self, request: "OrderRequest", mode: "ExecutionMode") -> "OrderResult":
        """Place a real order (SANDBOX or LIVE mode only — DRY_RUN is
        handled entirely inside OrderGateway and never reaches an
        adapter). Must never report status="SUBMITTED" unless the broker
        actually returned an order_id."""
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_broker_provider_protocols.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/market_data/provider.py backend/app/execution/broker_adapter.py backend/tests/test_broker_provider_protocols.py
git commit -m "feat: add broker-agnostic MarketDataProvider and BrokerExecutionAdapter protocols"
```

---

### Task 2: Active-broker registry (registration, persistence, selection, open-position guard)

**Files:**
- Create: `backend/app/core/active_broker.py`
- Test: `backend/tests/test_active_broker.py`

**Interfaces:**
- Consumes: `MarketDataProvider` and `BrokerExecutionAdapter` from Task 1; `is_known_broker` from `backend/app/core/broker_registry.py` (existing); `event_bus` from `backend/app/core/event_bus.py` (existing, `async def publish(channel: str, payload) -> None`).
- Produces: `ActiveBrokerRegistry` class and module-level singleton `active_broker`, with: `register_broker(broker_id: str, provider=None, execution_adapter=None, auth_module=None) -> None`, `register_position_checker(name: str, checker: Callable[[], Optional[str]]) -> None`, `is_broker_ready(broker_id: str) -> bool`, `get_active_broker_id() -> Optional[str]`, `get_active_provider() -> Optional[MarketDataProvider]`, `get_active_execution_adapter() -> Optional[BrokerExecutionAdapter]`, `get_active_auth_module() -> Optional[object]`, `blocking_open_positions() -> List[str]`, `async set_active_broker(broker_id: str) -> None` (raises `BrokerSwitchError`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_active_broker.py
import pytest

from backend.app.core import active_broker as ab_module
from backend.app.core.active_broker import ActiveBrokerRegistry, BrokerSwitchError


class _FakeAuth:
    def __init__(self, token):
        self._token = token

    def load_token(self):
        return self._token


class _FakeProvider:
    def __init__(self):
        self.connected = False
        self.disconnected = False

    def instrument_key_for_index(self, underlying):
        return f"FAKE|{underlying}"

    async def connect_feed(self):
        self.connected = True

    async def disconnect_feed(self):
        self.disconnected = True

    async def fetch_option_chain(self, index_key, access_token, expiry_date="current_week"):
        return []

    async def fetch_quote(self, instrument_key, access_token):
        return None

    async def fetch_historical_candles(self, instrument_key, access_token, to_date, from_date, interval="day"):
        return []


class _FakeAdapter:
    async def place_order(self, request, mode):
        return None


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(ab_module, "STATE_PATH", tmp_path / "active_broker.json")
    monkeypatch.setattr(ab_module.event_bus, "publish", _noop_publish)
    return ActiveBrokerRegistry()


_published = []


async def _noop_publish(channel, payload):
    _published.append((channel, payload))


def test_no_active_broker_initially(registry):
    assert registry.get_active_broker_id() is None
    assert registry.get_active_provider() is None
    assert registry.get_active_execution_adapter() is None


def test_is_broker_ready_false_until_fully_registered_and_connected(registry):
    assert registry.is_broker_ready("upstox") is False
    registry.register_broker("upstox", provider=_FakeProvider())
    assert registry.is_broker_ready("upstox") is False  # no adapter/auth yet
    registry.register_broker("upstox", execution_adapter=_FakeAdapter(), auth_module=_FakeAuth(None))
    assert registry.is_broker_ready("upstox") is False  # auth has no token
    registry.register_broker("upstox", auth_module=_FakeAuth("tok"))
    assert registry.is_broker_ready("upstox") is True


@pytest.mark.asyncio
async def test_set_active_broker_rejects_unknown_broker(registry):
    with pytest.raises(BrokerSwitchError):
        await registry.set_active_broker("not_a_real_broker")


@pytest.mark.asyncio
async def test_set_active_broker_rejects_not_ready_broker(registry):
    with pytest.raises(BrokerSwitchError):
        await registry.set_active_broker("upstox")


@pytest.mark.asyncio
async def test_set_active_broker_succeeds_and_connects_feed(registry):
    provider = _FakeProvider()
    registry.register_broker("upstox", provider=provider, execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok"))
    await registry.set_active_broker("upstox")
    assert registry.get_active_broker_id() == "upstox"
    assert registry.get_active_provider() is provider
    assert provider.connected is True


@pytest.mark.asyncio
async def test_active_broker_persists_across_new_registry_instance(tmp_path, monkeypatch):
    state_path = tmp_path / "active_broker.json"
    monkeypatch.setattr(ab_module, "STATE_PATH", state_path)
    monkeypatch.setattr(ab_module.event_bus, "publish", _noop_publish)

    first = ActiveBrokerRegistry()
    first.register_broker("upstox", provider=_FakeProvider(), execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok"))
    await first.set_active_broker("upstox")

    second = ActiveBrokerRegistry()
    assert second.get_active_broker_id() == "upstox"


@pytest.mark.asyncio
async def test_switching_broker_disconnects_previous_provider(registry):
    upstox_provider = _FakeProvider()
    zerodha_provider = _FakeProvider()
    registry.register_broker("upstox", provider=upstox_provider, execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok"))
    registry.register_broker("zerodha", provider=zerodha_provider, execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok2"))

    await registry.set_active_broker("upstox")
    await registry.set_active_broker("zerodha")

    assert upstox_provider.disconnected is True
    assert zerodha_provider.connected is True
    assert registry.get_active_broker_id() == "zerodha"


@pytest.mark.asyncio
async def test_switch_blocked_by_open_position(registry):
    registry.register_broker("upstox", provider=_FakeProvider(), execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok"))
    registry.register_broker("zerodha", provider=_FakeProvider(), execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok2"))
    await registry.set_active_broker("upstox")

    registry.register_position_checker("CAS Dislocation", lambda: "1 open position (NIFTY 25000 CE)")

    with pytest.raises(BrokerSwitchError, match="CAS Dislocation"):
        await registry.set_active_broker("zerodha")
    assert registry.get_active_broker_id() == "upstox"  # unchanged


@pytest.mark.asyncio
async def test_switch_allowed_when_checker_reports_no_blocker(registry):
    registry.register_broker("upstox", provider=_FakeProvider(), execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok"))
    registry.register_broker("zerodha", provider=_FakeProvider(), execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok2"))
    await registry.set_active_broker("upstox")

    registry.register_position_checker("CAS Dislocation", lambda: None)

    await registry.set_active_broker("zerodha")
    assert registry.get_active_broker_id() == "zerodha"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_active_broker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.core.active_broker'`

- [ ] **Step 3: Implement `active_broker.py`**

```python
# backend/app/core/active_broker.py
"""Single source of truth for which broker currently drives data feed and
order execution — a SaaS-style "connect one broker, everything uses it"
switch, confirmed with the user as the intended model (exactly one active
broker at a time, never multiple simultaneously). Strategy code,
order_gateway, and every market-data caller resolve "the active broker"
here rather than importing a specific broker's module — so switching the
active broker changes where data comes from and orders go without any
strategy code changing.

Persisted (unlike execution/runtime_state.py's LIVE arm switch, which
deliberately resets on restart as a safety measure) — broker selection is
not a safety switch, so it survives a process restart the same way saved
credentials do.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from backend.app.core.broker_registry import is_known_broker
from backend.app.core.event_bus import event_bus
from backend.app.execution.broker_adapter import BrokerExecutionAdapter
from backend.app.market_data.provider import MarketDataProvider

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_PATH = _BACKEND_ROOT / ".active_broker.json"


class BrokerSwitchError(Exception):
    """Raised when a broker cannot be made active — unknown broker, not
    ready (no provider/adapter registered, or not connected), or an open
    position would become unmanageable under a different broker."""


@dataclass
class _BrokerRegistration:
    broker_id: str
    provider: Optional[MarketDataProvider] = None
    execution_adapter: Optional[BrokerExecutionAdapter] = None
    auth_module: Optional[object] = None  # exposes load_token() -> Optional[str]


class ActiveBrokerRegistry:
    def __init__(self):
        self._registrations: Dict[str, _BrokerRegistration] = {}
        self._position_checkers: Dict[str, Callable[[], Optional[str]]] = {}
        self._active_broker_id: Optional[str] = self._load_persisted()

    # ---------------------- registration ----------------------

    def register_broker(
        self, broker_id: str, provider: Optional[MarketDataProvider] = None,
        execution_adapter: Optional[BrokerExecutionAdapter] = None,
        auth_module: Optional[object] = None,
    ) -> None:
        existing = self._registrations.get(broker_id)
        if existing is None:
            existing = _BrokerRegistration(broker_id=broker_id)
            self._registrations[broker_id] = existing
        if provider is not None:
            existing.provider = provider
        if execution_adapter is not None:
            existing.execution_adapter = execution_adapter
        if auth_module is not None:
            existing.auth_module = auth_module

    def register_position_checker(self, name: str, checker: Callable[[], Optional[str]]) -> None:
        """checker() returns None if that strategy has no open position
        blocking a broker switch, or a human-readable description of what
        is blocking it."""
        self._position_checkers[name] = checker

    def is_broker_ready(self, broker_id: str) -> bool:
        """True once a provider AND execution adapter are registered for
        broker_id AND its stored credentials produce a real token."""
        reg = self._registrations.get(broker_id)
        if reg is None or reg.provider is None or reg.execution_adapter is None or reg.auth_module is None:
            return False
        return reg.auth_module.load_token() is not None

    # ---------------------- active broker ----------------------

    def get_active_broker_id(self) -> Optional[str]:
        return self._active_broker_id

    def get_active_provider(self) -> Optional[MarketDataProvider]:
        reg = self._registrations.get(self._active_broker_id) if self._active_broker_id else None
        return reg.provider if reg else None

    def get_active_execution_adapter(self) -> Optional[BrokerExecutionAdapter]:
        reg = self._registrations.get(self._active_broker_id) if self._active_broker_id else None
        return reg.execution_adapter if reg else None

    def get_active_auth_module(self) -> Optional[object]:
        reg = self._registrations.get(self._active_broker_id) if self._active_broker_id else None
        return reg.auth_module if reg else None

    def blocking_open_positions(self) -> List[str]:
        blockers = []
        for name, checker in self._position_checkers.items():
            reason = checker()
            if reason:
                blockers.append(f"{name}: {reason}")
        return blockers

    async def set_active_broker(self, broker_id: str) -> None:
        if not is_known_broker(broker_id):
            raise BrokerSwitchError(f"Unknown broker: {broker_id!r}.")
        if not self.is_broker_ready(broker_id):
            raise BrokerSwitchError(
                f"{broker_id} is not connected, or has no data/execution integration registered yet."
            )

        switching_broker = broker_id != self._active_broker_id
        if switching_broker:
            blockers = self.blocking_open_positions()
            if blockers:
                raise BrokerSwitchError(
                    "Cannot switch active broker while positions are open: " + "; ".join(blockers)
                )

        previous_provider = self.get_active_provider()
        if switching_broker and previous_provider is not None:
            await previous_provider.disconnect_feed()

        self._active_broker_id = broker_id
        self._persist()

        new_provider = self.get_active_provider()
        if new_provider is not None:
            await new_provider.connect_feed()

        await event_bus.publish("broker_active_changed", {"broker_id": broker_id})
        logger.info("Active broker set to %s", broker_id)

    # ---------------------- persistence ----------------------

    def _load_persisted(self) -> Optional[str]:
        if not STATE_PATH.exists():
            return None
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return data.get("active_broker_id")

    def _persist(self) -> None:
        STATE_PATH.write_text(json.dumps({"active_broker_id": self._active_broker_id}), encoding="utf-8")


active_broker = ActiveBrokerRegistry()
```

Note: `STATE_PATH` is read as a module global inside `_load_persisted`/`_persist`, so `monkeypatch.setattr(ab_module, "STATE_PATH", ...)` in tests takes effect correctly as long as it's set *before* `ActiveBrokerRegistry()` is constructed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_active_broker.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/active_broker.py backend/tests/test_active_broker.py
git commit -m "feat: add persisted active-broker registry with open-position switch guard"
```

---

### Task 3: Upstox `MarketDataProvider` wrapper

**Files:**
- Create: `backend/app/market_data/upstox_provider.py`
- Test: `backend/tests/test_upstox_provider.py`

**Interfaces:**
- Consumes: `MarketDataProvider` protocol (Task 1); existing `upstox_client` (`market_data/upstox_v3.py`), `fetch_option_chain` (`market_data/option_chain_client.py`), `fetch_quote` (`market_data/market_quote.py`), `fetch_historical_candles` (`market_data/historical_candles.py`), `INDEX_INSTRUMENT_KEYS` (`market_data/symbols.py`) — all unchanged.
- Produces: `UpstoxProvider` class and module-level singleton `upstox_provider`, satisfying `MarketDataProvider`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_upstox_provider.py
from datetime import date
from unittest.mock import AsyncMock

import pytest

from backend.app.market_data import upstox_provider as up_module
from backend.app.market_data.provider import MarketDataProvider
from backend.app.market_data.upstox_provider import UpstoxProvider


def test_upstox_provider_satisfies_protocol():
    assert isinstance(UpstoxProvider(), MarketDataProvider)


def test_instrument_key_for_index_uses_symbols_mapping():
    provider = UpstoxProvider()
    assert provider.instrument_key_for_index("NIFTY") == "NSE_INDEX|Nifty 50"


@pytest.mark.asyncio
async def test_connect_feed_delegates_to_upstox_client(monkeypatch):
    provider = UpstoxProvider()
    mock_connect = AsyncMock()
    monkeypatch.setattr(up_module.upstox_client, "connect", mock_connect)
    await provider.connect_feed()
    mock_connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_feed_delegates_to_upstox_client_close(monkeypatch):
    provider = UpstoxProvider()
    mock_close = AsyncMock()
    monkeypatch.setattr(up_module.upstox_client, "close", mock_close)
    await provider.disconnect_feed()
    mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_option_chain_delegates_with_same_args(monkeypatch):
    provider = UpstoxProvider()
    mock_fetch = AsyncMock(return_value=[{"strike_price": 25000}])
    monkeypatch.setattr(up_module, "fetch_option_chain", mock_fetch)
    result = await provider.fetch_option_chain("NSE_INDEX|Nifty 50", "tok", "current_week")
    mock_fetch.assert_awaited_once_with("NSE_INDEX|Nifty 50", "tok", "current_week")
    assert result == [{"strike_price": 25000}]


@pytest.mark.asyncio
async def test_fetch_quote_delegates(monkeypatch):
    provider = UpstoxProvider()
    mock_fetch = AsyncMock(return_value="quote-object")
    monkeypatch.setattr(up_module, "fetch_quote", mock_fetch)
    result = await provider.fetch_quote("NSE_FO|123", "tok")
    mock_fetch.assert_awaited_once_with("NSE_FO|123", "tok")
    assert result == "quote-object"


@pytest.mark.asyncio
async def test_fetch_historical_candles_delegates(monkeypatch):
    provider = UpstoxProvider()
    mock_fetch = AsyncMock(return_value=[{"close": 100.0}])
    monkeypatch.setattr(up_module, "fetch_historical_candles", mock_fetch)
    to_date, from_date = date(2026, 1, 10), date(2026, 1, 1)
    result = await provider.fetch_historical_candles("NSE_INDEX|Nifty 50", "tok", to_date, from_date, "day")
    mock_fetch.assert_awaited_once_with("NSE_INDEX|Nifty 50", "tok", to_date, from_date, "day")
    assert result == [{"close": 100.0}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_upstox_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.market_data.upstox_provider'`

- [ ] **Step 3: Implement `upstox_provider.py`**

```python
# backend/app/market_data/upstox_provider.py
"""Upstox's MarketDataProvider implementation — a pure wrapper around the
existing, already-working upstox_v3 / option_chain_client / market_quote /
historical_candles / symbols modules. No logic changes here; this only
gives Upstox's existing behavior a broker-agnostic front door so
active_broker.get_active_provider() can return it exactly like it will
Dhan's or Zerodha's provider in a later phase.
"""

from datetime import date
from typing import Any, Dict, List

from .historical_candles import fetch_historical_candles
from .market_quote import fetch_quote
from .option_chain_client import fetch_option_chain
from .symbols import INDEX_INSTRUMENT_KEYS
from .upstox_v3 import upstox_client


class UpstoxProvider:
    def instrument_key_for_index(self, underlying: str) -> str:
        return INDEX_INSTRUMENT_KEYS[underlying]

    async def connect_feed(self) -> None:
        await upstox_client.connect()

    async def disconnect_feed(self) -> None:
        if hasattr(upstox_client, "close"):
            await upstox_client.close()

    async def fetch_option_chain(
        self, index_key: str, access_token: str, expiry_date: str = "current_week",
    ) -> List[Dict[str, Any]]:
        return await fetch_option_chain(index_key, access_token, expiry_date)

    async def fetch_quote(self, instrument_key: str, access_token: str):
        return await fetch_quote(instrument_key, access_token)

    async def fetch_historical_candles(
        self, instrument_key: str, access_token: str, to_date: date, from_date: date,
        interval: str = "day",
    ) -> List[Dict[str, Any]]:
        return await fetch_historical_candles(instrument_key, access_token, to_date, from_date, interval)


upstox_provider = UpstoxProvider()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_upstox_provider.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/market_data/upstox_provider.py backend/tests/test_upstox_provider.py
git commit -m "feat: wrap Upstox market data behind the MarketDataProvider interface"
```

---

### Task 4: Upstox `BrokerExecutionAdapter` + `order_gateway.py` dispatch refactor

**Files:**
- Create: `backend/app/execution/upstox_adapter.py`
- Modify: `backend/app/execution/order_gateway.py`
- Modify: `backend/tests/test_order_gateway.py`

**Interfaces:**
- Consumes: `BrokerExecutionAdapter` protocol (Task 1); `active_broker` singleton (Task 2); `OrderRequest`, `OrderResult`, `ExecutionMode` from `order_gateway.py` (existing, unchanged shapes).
- Produces: `UpstoxExecutionAdapter` class + singleton `upstox_execution_adapter` in `execution/upstox_adapter.py`. `order_gateway.OrderGateway.place_order` keeps its existing signature and DRY_RUN behavior; SANDBOX/LIVE now delegate to `active_broker.get_active_execution_adapter()`.

This task moves the SANDBOX/LIVE network-call logic (currently inline in `OrderGateway.place_order`, lines ~162–224 of the current file) into `UpstoxExecutionAdapter.place_order`, unchanged in substance. `resolve_mode()` stays in `order_gateway.py` (broker-agnostic).

- [ ] **Step 1: Write the failing test additions**

Add an autouse fixture to `backend/tests/test_order_gateway.py` that registers and activates the real Upstox adapter with `active_broker` — mirroring what `main.py`'s startup will do in Task 7. Add this near the top of the file, after the existing `_reset_runtime_arm_state` fixture:

```python
from backend.app.core import active_broker as ab_module
from backend.app.execution.upstox_adapter import upstox_execution_adapter


class _AlwaysTokenAuth:
    def load_token(self):
        return "test-token"  # SANDBOX/LIVE tests set their own real token expectation via monkeypatch


class _StubProvider:
    async def connect_feed(self):
        pass

    async def disconnect_feed(self):
        pass


@pytest.fixture(autouse=True)
def _activate_upstox_for_tests(monkeypatch, tmp_path):
    """order_gateway.place_order only needs an active execution adapter,
    not a running feed — set the registry's state directly rather than
    going through the full async set_active_broker() (which would also
    try to connect a feed and publish an event, neither of which matters
    here, and calling an async method from a sync autouse fixture would
    fight pytest-asyncio's own event loop management).
    """
    monkeypatch.setattr(ab_module, "STATE_PATH", tmp_path / "active_broker.json")
    registry = ab_module.ActiveBrokerRegistry()
    registry.register_broker(
        "upstox", provider=_StubProvider(), execution_adapter=upstox_execution_adapter,
        auth_module=_AlwaysTokenAuth(),
    )
    registry._active_broker_id = "upstox"
    monkeypatch.setattr(ab_module, "active_broker", registry)
    monkeypatch.setattr(gw_module, "active_broker", registry)
    yield
```

Then update the monkeypatch targets in the existing SANDBOX/LIVE/failure tests (`test_sandbox_submission_returns_order_id`, `test_sandbox_without_token_is_rejected_before_network`, `test_live_mode_targets_the_hft_host`, `test_broker_rejection_is_not_reported_as_submitted`, `test_transport_failure_reports_unknown_not_submitted`, `test_200_without_order_id_is_not_submitted`) to patch the new module instead of `order_gateway`:

```python
from backend.app.execution import upstox_adapter as ua_module

# e.g. in test_sandbox_submission_returns_order_id, replace:
#   monkeypatch.setattr(gw_module.httpx, "AsyncClient", _mock_client_factory(...))
# with:
#   monkeypatch.setattr(ua_module.httpx, "AsyncClient", _mock_client_factory(...))
# and in test_live_mode_targets_the_hft_host, replace:
#   monkeypatch.setattr(gw_module.upstox_auth, "load_token", lambda: "live-token")
# with:
#   monkeypatch.setattr(ua_module.upstox_auth, "load_token", lambda: "live-token")
```

(`test_sandbox_without_token_is_rejected_before_network` still patches `gw_module.httpx.AsyncClient` to `explode` — that assertion is still valid since the adapter is only reached when a token check inside it fails, and the adapter itself must not open a client either; change it to patch `ua_module.httpx.AsyncClient` instead, same `explode` body.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_order_gateway.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.execution.upstox_adapter'`

- [ ] **Step 3: Implement `upstox_adapter.py` and refactor `order_gateway.py`**

```python
# backend/app/execution/upstox_adapter.py
"""Upstox's BrokerExecutionAdapter implementation — the actual
network-calling order-placement logic, moved out of order_gateway.py
unchanged. order_gateway.OrderGateway.place_order still owns the DRY_RUN
short-circuit and the two-factor LIVE arm check (resolve_mode()); this
adapter is only ever reached for SANDBOX/LIVE.
"""

import logging
from typing import Optional

import httpx

from backend.app.core import upstox_auth
from backend.app.execution.order_gateway import ExecutionMode, OrderRequest, OrderResult

logger = logging.getLogger(__name__)

LIVE_ORDER_URL = "https://api-hft.upstox.com/v2/order/place"
SANDBOX_ORDER_URL = "https://api-sandbox.upstox.com/v2/order/place"


def _resolve_token(mode: ExecutionMode) -> Optional[str]:
    """Sandbox uses its own token (Upstox issues a separate sandbox-only
    token that cannot place live orders, and vice versa)."""
    if mode is ExecutionMode.SANDBOX:
        import os
        return os.environ.get("UPSTOX_SANDBOX_ACCESS_TOKEN")
    return upstox_auth.load_token()


class UpstoxExecutionAdapter:
    async def place_order(self, request: OrderRequest, mode: ExecutionMode) -> OrderResult:
        payload = request.to_payload()

        token = _resolve_token(mode)
        if not token:
            detail = (
                "No sandbox access token (set UPSTOX_SANDBOX_ACCESS_TOKEN)."
                if mode is ExecutionMode.SANDBOX
                else "No saved Upstox token — log in via /api/v1/brokers/upstox/login."
            )
            logger.error("Order rejected before submission: %s", detail)
            return OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)

        url = SANDBOX_ORDER_URL if mode is ExecutionMode.SANDBOX else LIVE_ORDER_URL

        if mode is ExecutionMode.LIVE:
            logger.warning(
                "PLACING A REAL LIVE ORDER (real money): %s %s x%s",
                request.transaction_type, request.instrument_token, request.quantity,
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            detail = f"Order request failed in transport: {exc}. Order status UNKNOWN — verify manually."
            logger.error(detail)
            return OrderResult(status="ERROR", mode=mode, payload=payload, detail=detail)

        if response.status_code != 200:
            detail = f"Broker rejected order ({response.status_code}): {response.text}"
            logger.error(detail)
            return OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)

        body = response.json()
        order_id = (body.get("data") or {}).get("order_id")
        if not order_id:
            detail = f"Broker returned 200 but no order_id: {body}. Order status UNKNOWN — verify manually."
            logger.error(detail)
            return OrderResult(status="ERROR", mode=mode, payload=payload, detail=detail)

        logger.info("Order accepted by broker (%s mode). order_id=%s", mode.value, order_id)
        return OrderResult(
            status="SUBMITTED", mode=mode, order_id=order_id, payload=payload,
            detail="Broker returned an order_id.",
        )


upstox_execution_adapter = UpstoxExecutionAdapter()
```

Now trim `order_gateway.py` down to a dispatcher. Replace the whole `OrderGateway.place_order` method and the module-level `_resolve_token` function with:

```python
# backend/app/execution/order_gateway.py — replace place_order and drop _resolve_token
from backend.app.core.active_broker import active_broker  # add to imports at top

class OrderGateway:
    def __init__(self):
        self.last_result: Optional[OrderResult] = None

    async def place_order(self, request: OrderRequest) -> OrderResult:
        mode = resolve_mode()
        payload = request.to_payload()

        if mode is ExecutionMode.DRY_RUN:
            logger.info(
                "[DRY_RUN] Would place order (no network call made): %s", payload
            )
            result = OrderResult(
                status="DRY_RUN", mode=mode, payload=payload,
                detail="DRY_RUN mode — no order was sent to any broker.",
            )
            self.last_result = result
            return result

        adapter = active_broker.get_active_execution_adapter()
        if adapter is None:
            detail = "No active broker — connect and activate a broker before placing real orders."
            logger.error("Order rejected before submission: %s", detail)
            result = OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)
            self.last_result = result
            return result

        result = await adapter.place_order(request, mode)
        self.last_result = result
        return result


order_gateway = OrderGateway()
```

Remove the now-unused `_resolve_token` function, the `LIVE_ORDER_URL`/`SANDBOX_ORDER_URL` constants, and the `httpx`/`upstox_auth` imports from `order_gateway.py` if nothing else in the file uses them (`resolve_mode()` doesn't need `httpx` or `upstox_auth`, only `os` and `execution_runtime_state`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_order_gateway.py -v`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/upstox_adapter.py backend/app/execution/order_gateway.py backend/tests/test_order_gateway.py
git commit -m "refactor: extract Upstox order placement into a BrokerExecutionAdapter, dispatch via active_broker"
```

---

### Task 5: Broker-neutral LIVE arm-switch env vars

**Files:**
- Modify: `backend/app/execution/order_gateway.py` (`resolve_mode()`)
- Modify: `backend/app/api/endpoints/execution_control.py`
- Modify: `backend/.env.example`
- Modify (comments only): `backend/app/engines/risk.py`, `backend/app/execution/runtime_state.py`, `backend/app/strategies/manual_trading/engine.py`
- Modify: `frontend/src/views/ExecutionControlView.tsx`
- Modify: `docs/order_flow_option_strategy_architecture.md`
- Modify: `backend/tests/test_order_gateway.py`, `backend/tests/test_execution_control_api.py`, `backend/tests/test_manual_trading_safety_chain.py`

**Interfaces:**
- No new interfaces — pure rename of two env var names: `UPSTOX_EXECUTION_MODE` → `EXECUTION_MODE`, `UPSTOX_LIVE_TRADING_CONFIRMED` → `LIVE_TRADING_CONFIRMED`. Confirmed with the user as broker-neutral (single active broker at a time means one arm switch applies to whichever broker that is).

- [ ] **Step 1: Update the failing tests first**

In `backend/tests/test_order_gateway.py`, replace every `"UPSTOX_EXECUTION_MODE"` with `"EXECUTION_MODE"` and every `"UPSTOX_LIVE_TRADING_CONFIRMED"` with `"LIVE_TRADING_CONFIRMED"` (10 occurrences across the mode-resolution and submission tests).

In `backend/tests/test_execution_control_api.py`, replace the `monkeypatch.delenv("UPSTOX_EXECUTION_MODE", raising=False)` call with `monkeypatch.delenv("EXECUTION_MODE", raising=False)`.

In `backend/tests/test_manual_trading_safety_chain.py`, replace `monkeypatch.delenv("UPSTOX_EXECUTION_MODE", raising=False)` with `monkeypatch.delenv("EXECUTION_MODE", raising=False)`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_order_gateway.py backend/tests/test_execution_control_api.py backend/tests/test_manual_trading_safety_chain.py -v`
Expected: FAIL — tests now set `EXECUTION_MODE`/`LIVE_TRADING_CONFIRMED` but the code still reads the old `UPSTOX_`-prefixed names, so LIVE/SANDBOX tests fall back to DRY_RUN unexpectedly.

- [ ] **Step 3: Rename the env vars in code**

In `backend/app/execution/order_gateway.py`, inside `resolve_mode()`:

```python
    raw = (os.environ.get("EXECUTION_MODE") or "DRY_RUN").strip().upper()
    ...
    if mode is ExecutionMode.LIVE:
        confirmed = (os.environ.get("LIVE_TRADING_CONFIRMED") or "").strip().upper()
```

Update the module docstring's mentions of `UPSTOX_EXECUTION_MODE`/`UPSTOX_LIVE_TRADING_CONFIRMED` to the new names.

In `backend/app/api/endpoints/execution_control.py`, line 36:

```python
    env_mode = (os.environ.get("EXECUTION_MODE") or "DRY_RUN").strip().upper()
```

Update its module docstring comment mentioning `UPSTOX_EXECUTION_MODE` too.

In `backend/.env.example`, rename:

```
# LIVE additionally requires LIVE_TRADING_CONFIRMED=YES below, so ...
EXECUTION_MODE=DRY_RUN
...
LIVE_TRADING_CONFIRMED=
```

Update the doc-comment mentions in `backend/app/engines/risk.py` (line ~74), `backend/app/execution/runtime_state.py` (line ~4), and `backend/app/strategies/manual_trading/engine.py` (line ~8) from `UPSTOX_EXECUTION_MODE=LIVE` to `EXECUTION_MODE=LIVE` — comment text only, no logic change.

In `frontend/src/views/ExecutionControlView.tsx` line 155, change the displayed `<code>` text from `UPSTOX_EXECUTION_MODE=LIVE` to `EXECUTION_MODE=LIVE`.

In `docs/order_flow_option_strategy_architecture.md`, update any `UPSTOX_EXECUTION_MODE`/`UPSTOX_LIVE_TRADING_CONFIRMED` mentions to the new names for consistency.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_order_gateway.py backend/tests/test_execution_control_api.py backend/tests/test_manual_trading_safety_chain.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend/app/execution/order_gateway.py backend/app/api/endpoints/execution_control.py backend/.env.example backend/app/engines/risk.py backend/app/execution/runtime_state.py backend/app/strategies/manual_trading/engine.py frontend/src/views/ExecutionControlView.tsx docs/order_flow_option_strategy_architecture.md backend/tests/test_order_gateway.py backend/tests/test_execution_control_api.py backend/tests/test_manual_trading_safety_chain.py
git commit -m "refactor: rename LIVE arm-switch env vars to broker-neutral EXECUTION_MODE/LIVE_TRADING_CONFIRMED"
```

---

### Task 6: Open-position queries for CAS Dislocation, Manual Trading, OFAO

**Files:**
- Modify: `backend/app/strategies/cas_dislocation/engine.py`
- Modify: `backend/app/strategies/manual_trading/engine.py`
- Modify: `backend/app/strategies/order_flow_absorption/state_machine.py`
- Modify: `backend/app/strategies/order_flow_absorption/engine.py`
- Test: append to `backend/tests/strategies/order_flow_absorption/test_state_machine.py`; new small tests added directly under existing test files for CAS/manual trading (see below).

**Interfaces:**
- Produces: `CASDislocationEngine.get_open_position_blocker(self) -> Optional[str]`, `ManualTradingEngine.get_open_position_blocker(self) -> Optional[str]`, `OFAOStateMachine.has_any_active_setup(self) -> bool`, `OFAOEngine.get_open_position_blocker(self) -> Optional[str]`. Each returns `None` when nothing is blocking, or a short human-readable description otherwise — this is exactly the `Callable[[], Optional[str]]` shape `active_broker.register_position_checker` expects (Task 2).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/strategies/order_flow_absorption/test_state_machine.py`:

```python
def test_has_any_active_setup_false_when_all_no_setup():
    sm = OFAOStateMachine()
    sm.get("NIFTY FUT")
    assert sm.has_any_active_setup() is False


def test_has_any_active_setup_true_when_one_instrument_in_flight():
    sm = OFAOStateMachine()
    sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, direction=SetupDirection.BULL, location_price=100.0)
    assert sm.has_any_active_setup() is True
```

Add a new file `backend/tests/test_cas_manual_ofao_position_blockers.py`:

```python
from backend.app.strategies.cas_dislocation.engine import CASDislocationEngine
from backend.app.strategies.cas_dislocation.models import CASPosition
from backend.app.strategies.manual_trading.engine import ManualTradingEngine
from backend.app.strategies.manual_trading.models import ManualPosition
from backend.app.strategies.order_flow_absorption.engine import OFAOEngine
from backend.app.strategies.order_flow_absorption.models import SetupDirection, SetupState


def test_cas_blocker_none_when_no_positions():
    engine = CASDislocationEngine()
    assert engine.get_open_position_blocker() is None


def test_cas_blocker_reports_open_positions():
    engine = CASDislocationEngine()
    engine.positions["p1"] = CASPosition(
        position_id="p1", underlying="NIFTY", strike=25000, option_type="CE",
        instrument_token="NSE_FO|1", quantity=75, entry_price=100.0, status="OPEN",
    )
    blocker = engine.get_open_position_blocker()
    assert blocker is not None
    assert "1" in blocker


def test_manual_trading_blocker_none_when_no_positions():
    engine = ManualTradingEngine()
    assert engine.get_open_position_blocker() is None


def test_manual_trading_blocker_reports_open_positions():
    engine = ManualTradingEngine()
    engine.positions["p1"] = ManualPosition(
        position_id="p1", underlying="NIFTY", strike=25000, option_type="CE",
        instrument_token="NSE_FO|1", quantity=75, entry_price=100.0, status="OPEN",
    )
    blocker = engine.get_open_position_blocker()
    assert blocker is not None


def test_ofao_blocker_none_when_no_active_setup():
    engine = OFAOEngine()
    assert engine.get_open_position_blocker() is None


def test_ofao_blocker_reports_active_setup():
    engine = OFAOEngine()
    engine.state_machine.transition(
        "NIFTY FUT", SetupState.LOCATION_REACHED, direction=SetupDirection.BULL, location_price=100.0,
    )
    blocker = engine.get_open_position_blocker()
    assert blocker is not None
    assert "NIFTY FUT" in blocker
```

(Check the exact required constructor fields for `CASPosition`/`ManualPosition` against `backend/app/strategies/cas_dislocation/models.py` and `backend/app/strategies/manual_trading/models.py` before running — add any other required fields those models declare; the fields above are the ones known from this plan's investigation, not necessarily exhaustive.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/strategies/order_flow_absorption/test_state_machine.py backend/tests/test_cas_manual_ofao_position_blockers.py -v`
Expected: FAIL — `AttributeError: 'OFAOStateMachine' object has no attribute 'has_any_active_setup'` (and similarly for the other two `get_open_position_blocker` calls).

- [ ] **Step 3: Implement the methods**

In `backend/app/strategies/order_flow_absorption/state_machine.py`, add to `OFAOStateMachine`:

```python
    def has_any_active_setup(self) -> bool:
        return any(
            ctx.state != SetupState.NO_SETUP and ctx.state not in TERMINAL_STATES
            for ctx in self._contexts.values()
        )
```

In `backend/app/strategies/order_flow_absorption/engine.py`, add to `OFAOEngine`:

```python
    def get_open_position_blocker(self) -> Optional[str]:
        active = [
            instrument for instrument, ctx in self.state_machine._contexts.items()
            if ctx.state != SetupState.NO_SETUP and ctx.state not in TERMINAL_STATES
        ]
        if not active:
            return None
        return f"{len(active)} active setup(s): {', '.join(active)}."
```

(Add `TERMINAL_STATES` to the existing `from .models import ...` import line in `engine.py` if not already imported.)

In `backend/app/strategies/cas_dislocation/engine.py`, add near `_has_active_position`:

```python
    def get_open_position_blocker(self) -> Optional[str]:
        open_positions = [p for p in self.positions.values() if p.status in ("PENDING", "OPEN")]
        if not open_positions:
            return None
        return f"{len(open_positions)} open position(s): " + ", ".join(
            f"{p.underlying} {p.strike} {p.option_type}" for p in open_positions
        )
```

In `backend/app/strategies/manual_trading/engine.py`, add near the other position-querying methods:

```python
    def get_open_position_blocker(self) -> Optional[str]:
        open_positions = [p for p in self.positions.values() if p.status == "OPEN"]
        if not open_positions:
            return None
        return f"{len(open_positions)} open position(s): " + ", ".join(
            f"{p.underlying} {p.strike} {p.option_type}" for p in open_positions
        )
```

Add `from typing import Optional` to each file's imports if not already present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/strategies/order_flow_absorption/test_state_machine.py backend/tests/test_cas_manual_ofao_position_blockers.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend/app/strategies/order_flow_absorption/state_machine.py backend/app/strategies/order_flow_absorption/engine.py backend/app/strategies/cas_dislocation/engine.py backend/app/strategies/manual_trading/engine.py backend/tests/strategies/order_flow_absorption/test_state_machine.py backend/tests/test_cas_manual_ofao_position_blockers.py
git commit -m "feat: add open-position queries to CAS/Manual/OFAO for the active-broker switch guard"
```

---

### Task 7: Wire `active_broker` into `main.py` startup/shutdown

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_main_broker_startup.py`

**Interfaces:**
- Consumes: everything produced by Tasks 2, 3, 4, 6.
- Produces: at startup, `active_broker` has Upstox registered; if Upstox has a saved token and no active broker is already persisted, Upstox becomes active automatically (preserves today's exact behavior — Upstox always connects on startup if a token exists); the live feed connects only through `active_broker.get_active_provider()`, never unconditionally.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_main_broker_startup.py
import pytest

from backend.app.core import active_broker as ab_module


@pytest.mark.asyncio
async def test_upstox_registered_at_import_time():
    # main.py registers upstox with active_broker at import time (via
    # upstox_provider/upstox_adapter/upstox_auth) regardless of whether a
    # token is saved — readiness (is_broker_ready) is what gates activation.
    import backend.app.main  # noqa: F401 — import triggers registration
    assert "upstox" in ab_module.active_broker._registrations
    reg = ab_module.active_broker._registrations["upstox"]
    assert reg.provider is not None
    assert reg.execution_adapter is not None
    assert reg.auth_module is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_main_broker_startup.py -v`
Expected: FAIL — `main.py` does not register anything with `active_broker` yet.

- [ ] **Step 3: Wire `main.py`**

Replace the import block (around line 53-54):

```python
from backend.app.market_data.upstox_provider import upstox_provider
from backend.app.execution.upstox_adapter import upstox_execution_adapter
from backend.app.core import upstox_auth
from backend.app.core.active_broker import active_broker

# Registering here (module import time) means active_broker knows about
# Upstox as soon as the app process exists — readiness (is_broker_ready)
# still gates whether it can actually be activated.
active_broker.register_broker(
    "upstox", provider=upstox_provider, execution_adapter=upstox_execution_adapter, auth_module=upstox_auth,
)
```

Replace the startup feed-connect block (lines ~126-131):

```python
    # If no broker has been explicitly activated yet but Upstox already
    # has a saved token, activate it automatically — this preserves
    # today's exact behavior (Upstox always connects on startup if a
    # token exists) under the new multi-broker model.
    if active_broker.get_active_broker_id() is None and active_broker.is_broker_ready("upstox"):
        await active_broker.set_active_broker("upstox")
    elif active_broker.get_active_broker_id() and active_broker.get_active_provider():
        # A broker was already active from a previous run (persisted) —
        # (re)connect its feed now that the process has restarted.
        await active_broker.get_active_provider().connect_feed()
    # If neither branch applies (no broker ready/active), the app starts
    # with no live feed rather than silently defaulting to one.

    # Register position checkers so switching the active broker is
    # blocked while any of these has an open position/setup.
    active_broker.register_position_checker("CAS Dislocation", cas_dislocation_engine.get_open_position_blocker)
    active_broker.register_position_checker("Manual Trading", manual_trading_engine.get_open_position_blocker)
    active_broker.register_position_checker("OFAO", ofao_engine.get_open_position_blocker)
```

Remove the now-unused `from backend.app.market_data.upstox_v3 import upstox_client` import (it's used only inside `upstox_provider.py` now) and the `saved_token = upstox_auth.load_token(); if saved_token: upstox_client.configure(saved_token); asyncio.create_task(upstox_client.connect())` block it replaced.

Replace the shutdown block (lines ~230-231):

```python
        if active_broker.get_active_provider() is not None:
            await active_broker.get_active_provider().disconnect_feed()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_main_broker_startup.py -v`
Expected: 1 passed

- [ ] **Step 5: Run the full suite to check for import-order regressions, then commit**

Run: `python -m pytest -q`
Expected: 885 passed, 3 pre-existing failures (same three as the Global Constraints baseline)

```bash
git add backend/app/main.py backend/tests/test_main_broker_startup.py
git commit -m "feat: wire active_broker into app startup/shutdown, auto-activating Upstox when connected"
```

---

### Task 8: Migrate strategy engine call sites off direct Upstox imports

**Files:**
- Modify: `backend/app/strategies/cas_dislocation/engine.py`
- Modify: `backend/app/strategies/expiry_engine.py`
- Modify: `backend/app/strategies/expiry_reversal/engine.py`
- Modify: `backend/app/strategies/manual_trading/engine.py`
- Modify: `backend/app/strategies/option_analytics/engine.py`
- Modify: `backend/app/strategies/order_flow_absorption/engine.py`

**Interfaces:**
- Consumes: `active_broker.get_active_provider()` / `get_active_auth_module()` (Task 2).
- Produces: no change to any function's external behavior — purely redirects where data comes from, from a hardcoded Upstox import to whichever broker is active.

This task is mechanical: each file's `token = upstox_auth.load_token()` becomes a call through the active broker's auth module, and each direct `fetch_option_chain(...)` / `fetch_quote(...)` / `INDEX_INSTRUMENT_KEYS[...]` call becomes a call through the active provider. No test changes are needed if the existing tests already mock these call sites at the strategy-module level (e.g. `patch("...engine.upstox_auth.load_token", ...)`) — those must be updated to patch `active_broker.get_active_auth_module`/`get_active_provider` instead. Check each file's existing tests before editing and update their patch targets in the same commit as that file's migration.

- [ ] **Step 1: `backend/app/strategies/cas_dislocation/engine.py`**

Replace the imports (lines 28, 36-41):

```python
from backend.app.core.active_broker import active_broker
from backend.app.market_data.market_quote import MarketQuoteLookupError
from backend.app.market_data.option_chain_client import OptionChainLookupError
```

(Drop `upstox_auth`, `fetch_quote`, `fetch_option_chain`, `INDEX_INSTRUMENT_KEYS` imports — they're now reached through the active provider/auth module.)

Replace the body around lines 148-165:

```python
        config = cas_config_state.get()
        provider = active_broker.get_active_provider()
        auth = active_broker.get_active_auth_module()
        if provider is None or auth is None:
            await self._publish_inactive(now_ist, "No active broker.")
            return
        token = auth.load_token()
        if not token:
            ...  # unchanged existing "no token" handling

        try:
            chain = await provider.fetch_option_chain(provider.instrument_key_for_index(config.underlying), token, "current_week")
            future_key = await futures_instrument_cache.get(config.underlying, token)
            future_quote = await provider.fetch_quote(future_key, token)
        except (OptionChainLookupError, FuturesInstrumentLookupError, MarketQuoteLookupError) as exc:
            ...  # unchanged existing exception handling
```

Update `backend/tests/test_btst_cas_engine.py` (and any other CAS test patching `cas_dislocation.engine.upstox_auth`/`fetch_option_chain`/`fetch_quote`/`INDEX_INSTRUMENT_KEYS`) to instead register a fake provider/auth module with `active_broker` and activate it in the test's setup, following the pattern from Task 2's tests.

- [ ] **Step 2: `backend/app/strategies/expiry_engine.py`**

Replace the token-fetch and option-chain-fetch call sites (lines ~164-171) with the same `active_broker.get_active_provider()` / `get_active_auth_module()` pattern as Task 8 Step 1 — `fetch_option_chain(self.underlying_key, token, "current_week")` becomes `provider.fetch_option_chain(self.underlying_key, token, "current_week")` (this file already resolves `self.underlying_key` itself, so no `instrument_key_for_index` call is needed here).

- [ ] **Step 3: `backend/app/strategies/expiry_reversal/engine.py`**

Replace `token = upstox_auth.load_token()` (line 104) with `auth = active_broker.get_active_auth_module(); token = auth.load_token() if auth else None`.

- [ ] **Step 4: `backend/app/strategies/manual_trading/engine.py`**

Replace the imports (`from backend.app.core import upstox_auth`, `from backend.app.market_data.symbols import INDEX_INSTRUMENT_KEYS`, the `fetch_option_chain` import) with `from backend.app.core.active_broker import active_broker`.

Replace `_require_token` (lines 93-95):

```python
    async def _require_token(self) -> str:
        auth = active_broker.get_active_auth_module()
        token = auth.load_token() if auth else None
        if not token:
            ...  # unchanged existing "no token" ManualTradingError
        return token
```

Replace the option-chain lookup block (lines 105-119):

```python
        provider = active_broker.get_active_provider()
        if provider is None:
            raise ManualTradingError(f"No active broker — cannot resolve {underlying}.")
        if underlying not in [k for k in ("NIFTY", "SENSEX", "BANKNIFTY")]:  # unchanged existing validation, keep as-is
            raise ManualTradingError(
                f"Unsupported underlying {underlying!r} — must be one of "
                f"{sorted(('NIFTY', 'SENSEX', 'BANKNIFTY'))}."
            )
        instrument_key = provider.instrument_key_for_index(underlying)
        try:
            return await provider.fetch_option_chain(instrument_key, token, expiry_date)
        except OptionChainLookupError as exc:
            ...  # unchanged existing fallback handling
            if expiry_date == "current_week":
                try:
                    return await provider.fetch_option_chain(instrument_key, token, "next_week")
                except OptionChainLookupError as fallback_exc:
                    ...  # unchanged existing fallback handling
```

(Keep the existing validation message's exact wording — only the `INDEX_INSTRUMENT_KEYS.keys()` source of truth changes; since this file no longer imports `INDEX_INSTRUMENT_KEYS` directly, replace `sorted(INDEX_INSTRUMENT_KEYS.keys())` with the same literal tuple used above, `sorted(("NIFTY", "SENSEX", "BANKNIFTY"))`, to avoid re-adding the direct import — check the file's actual current wording before editing so the message text doesn't unintentionally change.)

Replace the monitor loop's token fetch (line 371):

```python
                    auth = active_broker.get_active_auth_module()
                    token = auth.load_token() if auth else None
                    if token:
```

- [ ] **Step 5: `backend/app/strategies/option_analytics/engine.py`**

Replace the option-chain fetch (lines 113-115), the historical-candles fetch (lines 130-131), and the token fetch (line 336) with the `active_broker` equivalents.

- [ ] **Step 6: `backend/app/strategies/order_flow_absorption/engine.py`**

Replace lines 32/35/36 imports and the body at lines 424/435 (`token = upstox_auth.load_token()`, `INDEX_INSTRUMENT_KEYS.get(underlying)`, `fetch_option_chain(index_key, token, "current_week")`) with the `active_broker` equivalents, inside `_resolve_and_submit`. Update `backend/tests/strategies/order_flow_absorption/test_ofao_engine_pipeline.py`'s patches (`patch("...engine.upstox_auth.load_token", ...)`, `patch("...engine.fetch_option_chain", ...)`) to instead register a fake provider/auth with `active_broker` for the test.

- [ ] **Step 7: Run all affected tests**

Run: `python -m pytest backend/tests/test_btst_cas_engine.py backend/tests/strategies/order_flow_absorption/ backend/tests/test_manual_trading_safety_chain.py backend/tests/strategies/test_straddle_engine.py -v`
Expected: all pass (fix any test that still patches an old direct-import target until they do)

- [ ] **Step 8: Run the full suite**

Run: `python -m pytest -q`
Expected: 885 passed, 3 pre-existing failures

- [ ] **Step 9: Commit**

```bash
git add backend/app/strategies/cas_dislocation/engine.py backend/app/strategies/expiry_engine.py backend/app/strategies/expiry_reversal/engine.py backend/app/strategies/manual_trading/engine.py backend/app/strategies/option_analytics/engine.py backend/app/strategies/order_flow_absorption/engine.py backend/tests
git commit -m "refactor: migrate strategy engines from direct Upstox imports to active_broker"
```

---

### Task 9: `GET`/`POST /api/v1/brokers/active`, and fix the legacy Upstox-only callback

**Files:**
- Modify: `backend/app/api/endpoints/brokers.py`
- Modify: `backend/app/api/endpoints/broker.py`
- Test: `backend/tests/test_brokers_active_api.py`

**Interfaces:**
- Produces: `GET /api/v1/brokers/active -> {"broker_id": Optional[str]}`; `POST /api/v1/brokers/active {"broker_id": str} -> {"broker_id": str, "active": true}` or `400` with the `BrokerSwitchError` message.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_brokers_active_api.py
import pytest
from fastapi.testclient import TestClient

from backend.app.core import active_broker as ab_module
from backend.app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ab_module, "STATE_PATH", tmp_path / "active_broker.json")
    monkeypatch.setattr(ab_module.active_broker, "_active_broker_id", None)
    return TestClient(app)


def test_get_active_broker_starts_as_null(client):
    res = client.get("/api/v1/brokers/active")
    assert res.status_code == 200
    assert res.json() == {"broker_id": None}


def test_post_active_broker_rejects_unknown_broker(client):
    res = client.post("/api/v1/brokers/active", json={"broker_id": "not_real"})
    assert res.status_code == 400


def test_post_active_broker_rejects_unready_broker(client):
    res = client.post("/api/v1/brokers/active", json={"broker_id": "dhan"})
    assert res.status_code == 400
    assert "not connected" in res.json()["detail"] or "registered" in res.json()["detail"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_brokers_active_api.py -v`
Expected: FAIL with 404 (routes don't exist yet)

- [ ] **Step 3: Implement the routes**

Add to `backend/app/api/endpoints/brokers.py` (after the existing imports, add `from backend.app.core.active_broker import active_broker, BrokerSwitchError`, and a request model):

```python
class SetActiveBrokerRequest(BaseModel):
    broker_id: str


@router.get("/active")
async def get_active_broker():
    return {"broker_id": active_broker.get_active_broker_id()}


@router.post("/active")
async def set_active_broker(req: SetActiveBrokerRequest):
    try:
        await active_broker.set_active_broker(req.broker_id)
    except BrokerSwitchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"broker_id": req.broker_id, "active": True}
```

(Place these routes before the `/{broker_id}/status` route in the file, since FastAPI matches `/active` against `/{broker_id}/status`'s `{broker_id}` path param first if declared afterward — put the literal `/active` routes above any `/{broker_id}/...` route in the file.)

In `backend/app/api/endpoints/broker.py`, remove the feed-connect side effect from the callback so the legacy Upstox-only login path stays consistent with "connecting only happens via active-broker activation":

```python
@router.get("/callback")
async def upstox_callback(code: str = Query(...), state: str = Query(None)):
    logger.info("Received Upstox callback")

    try:
        token = await upstox_auth.exchange_code_for_token(code)
        upstox_auth.save_token(token)
    except upstox_auth.UpstoxAuthError as exc:
        logger.error(f"Upstox token exchange failed: {exc}")
        return HTMLResponse(content=_result_page("ERROR", str(exc)), status_code=502)
    except Exception:
        logger.exception("Upstox connection setup failed")
        return HTMLResponse(
            content=_result_page("ERROR", "Failed to complete Upstox connection setup"),
            status_code=500,
        )

    return HTMLResponse(content=_result_page("CONNECTED"))
```

Remove the now-unused `from backend.app.market_data.upstox_v3 import upstox_client` import from `broker.py`, and the `configured = upstox_client.configure(token)` / `await upstox_client.connect()` calls and the `if not configured:` branch that reported mock mode (token saving no longer implies connecting).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_brokers_active_api.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the full suite, then commit**

Run: `python -m pytest -q`
Expected: 885 passed, 3 pre-existing failures

```bash
git add backend/app/api/endpoints/brokers.py backend/app/api/endpoints/broker.py backend/tests/test_brokers_active_api.py
git commit -m "feat: add GET/POST /api/v1/brokers/active; stop the legacy Upstox callback from auto-connecting the feed"
```

---

### Task 10: Frontend — active-broker indicator and "Make Active" action

**Files:**
- Modify: `frontend/src/views/BrokerConnectionsView.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/brokers/active`, `POST /api/v1/brokers/active` (Task 9).

- [ ] **Step 1: Add active-broker state and fetch**

In `BrokerConnectionsView.tsx`, add state and a fetch function alongside the existing `fetchBrokers`:

```tsx
const [activeBrokerId, setActiveBrokerId] = useState<string | null>(null);

const fetchActiveBroker = useCallback(async () => {
  try {
    const res = await fetch(`${API_BASE}/api/v1/brokers/active`);
    if (!res.ok) return;
    const data = await res.json();
    setActiveBrokerId(data.broker_id);
  } catch {
    // non-fatal — the connections list still renders without this
  }
}, []);

useEffect(() => {
  fetchActiveBroker();
}, [fetchActiveBroker]);
```

- [ ] **Step 2: Add the "Make Active" handler**

```tsx
const handleMakeActive = async () => {
  if (!active) return;
  setBusy(true);
  setError(null);
  setNotice(null);
  try {
    const res = await fetch(`${API_BASE}/api/v1/brokers/active`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ broker_id: active.id }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to activate broker');
    setNotice(`${active.display_name} is now the active broker.`);
    setActiveBrokerId(active.id);
  } catch (e) {
    setError(e instanceof Error ? e.message : 'Failed to activate broker');
  } finally {
    setBusy(false);
  }
};
```

- [ ] **Step 3: Render the active-broker badge on each tab and the "Make Active" button**

In the broker-tab row, add an "ACTIVE" badge next to the connected indicator:

```tsx
{brokers.map((b) => (
  <button key={b.id} /* ...unchanged... */>
    <Link2 size={14} className={b.connected ? 'text-emerald-400' : 'text-zinc-600'} />
    {b.display_name}
    <StatusBadge status={b.connected ? 'CONNECTED' : 'DISCONNECTED'} />
    {activeBrokerId === b.id && (
      <span className="text-[9px] font-bold text-amber-400 border border-amber-400/30 rounded px-1.5 py-0.5">
        ACTIVE
      </span>
    )}
  </button>
))}
```

In the credentials panel's action row, add the "Make Active" button next to Disconnect, enabled only when connected and not already active:

```tsx
{active.connected && activeBrokerId !== active.id && (
  <button
    onClick={handleMakeActive}
    disabled={busy}
    className="flex-1 py-2 px-3 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded hover:bg-amber-500/20 disabled:opacity-40 transition-colors text-xs font-bold"
  >
    MAKE ACTIVE
  </button>
)}
```

Update the page's descriptive text (line ~150-153) from "Only Upstox currently drives live strategies and order placement — Zerodha and Dhan store validated credentials for future use." to "Whichever broker is marked ACTIVE drives live data and order execution for the whole platform — connect a broker, then make it active."

- [ ] **Step 4: Verify in the browser**

Start the dev server (`preview_start` with the project's frontend launch config), navigate to the Broker Connections page, confirm: the ACTIVE badge shows on Upstox after Task 7's auto-activation (if a token is saved), clicking "Make Active" on a not-ready broker (Dhan/Zerodha, since Phase 2/3 aren't built yet) shows the 400 error message from the backend, and no console errors appear.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/BrokerConnectionsView.tsx
git commit -m "feat: add active-broker indicator and Make Active action to Broker Connections page"
```

---

### Task 11: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the complete backend suite**

Run: `python -m pytest -q`
Expected: 885 passed, exactly the same 3 pre-existing failures as the Global Constraints baseline (`test_bullish_setup`, `test_full_event_flow`, `test_candle_aggregation_no_look_ahead`) — no new failures, no tests newly passing that would suggest an accidental behavior change elsewhere.

- [ ] **Step 2: Run the frontend test suite**

Run: `npm test` (or the project's configured frontend test command) from `frontend/`.
Expected: all existing tests pass.

- [ ] **Step 3: Manual smoke check with Upstox as the only broker**

With a real or previously-saved Upstox token present, start the backend and frontend, confirm: the app starts with Upstox auto-activated (Task 7), live data continues to flow to the dashboard exactly as before this phase, and DRY_RUN order placement (the default) still logs a payload without any network call.

- [ ] **Step 4: If any regression is found, fix it and re-run Steps 1-3 before considering this phase complete.**

- [ ] **Step 5: Final commit (if any fixes were needed) — otherwise this task closes Phase 1**

```bash
git add -A
git commit -m "chore: verify Phase 1 multi-broker plumbing introduces no regressions"
```
