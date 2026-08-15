# Upstox OAuth + Live Spot Feed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mocked Upstox OAuth flow and mock-mode market-data client with real Upstox API calls, so `/login` → `/callback` performs a real OAuth exchange, the token is persisted locally, and the live V3 feed streams real NIFTY/BANKNIFTY/SENSEX spot ticks onto the existing `MARKET_TICK` event-bus topic.

**Architecture:** A new `backend/app/core/upstox_auth.py` owns OAuth URL-building, token exchange (`httpx`), and local token persistence (`backend/.token.json`). `UpstoxV3Client` gains a `configure(access_token)` method that swaps it from mock mode into a real `MarketDataStreamerV3`-backed client in place, so the existing module-level singleton (moved from `main.py` into `upstox_v3.py` to avoid a circular import with `broker.py`) keeps working for every consumer. `broker.py`'s `/login` and `/callback` call into `upstox_auth` and `upstox_client.configure()`; `main.py`'s startup loads any saved token before connecting.

**Tech Stack:** FastAPI, `httpx` (async token exchange), `upstox-python-sdk` (`upstox_client` package — `ApiClient`, `Configuration`, `MarketDataStreamerV3`), `python-dotenv`, `pytest` + `pytest-asyncio` + `unittest.mock`.

## Global Constraints

- No option-chain / per-strike subscription — only the three index spot instrument keys (`NSE_INDEX|Nifty 50`, `NSE_INDEX|Nifty Bank`, `BSE_INDEX|SENSEX`).
- No refresh-token flow — Upstox tokens expire daily and are not auto-refreshed; a stale/missing token falls back to today's existing mock-mode behavior (log warning, no crash).
- No encrypted token storage — `backend/.token.json` is a plain local JSON file, gitignored.
- No test may make a real network call to Upstox — `httpx` and the SDK are mocked at their boundary in every test.
- `TOKEN_PATH` resolves relative to the `upstox_auth.py` module's own file location, not the process's current working directory (the repo already has one CWD-dependent inconsistency between `README.md`'s documented run command and `main.py`'s imports; don't add a second one).

---

## Task 1: Instrument keys, dependencies, and env config

**Files:**
- Create: `backend/app/market_data/symbols.py`
- Create: `backend/tests/test_symbols.py`
- Create: `backend/.env.example`
- Modify: `backend/requirements.txt`
- Modify: `.gitignore:88-95`

**Interfaces:**
- Produces: `INDEX_INSTRUMENT_KEYS: dict[str, str]` — mapping of `"NIFTY"`/`"BANKNIFTY"`/`"SENSEX"` to their Upstox instrument key strings. Later tasks (`upstox_v3.py`, `main.py`) import this.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_symbols.py`:

```python
from backend.app.market_data.symbols import INDEX_INSTRUMENT_KEYS


def test_index_instrument_keys():
    assert INDEX_INSTRUMENT_KEYS == {
        "NIFTY": "NSE_INDEX|Nifty 50",
        "BANKNIFTY": "NSE_INDEX|Nifty Bank",
        "SENSEX": "BSE_INDEX|SENSEX",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_symbols.py -v` (from `D:/sanate`)
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.market_data.symbols'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/market_data/symbols.py`:

```python
INDEX_INSTRUMENT_KEYS = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "SENSEX": "BSE_INDEX|SENSEX",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_symbols.py -v`
Expected: PASS

- [ ] **Step 5: Add dependencies**

In `backend/requirements.txt`, append two lines after `pytest-asyncio`:

```
upstox-python-sdk
python-dotenv
```

Install them:

```bash
cd D:/sanate && .venv/Scripts/python.exe -m pip install upstox-python-sdk python-dotenv
```

- [ ] **Step 6: Verify the SDK's real attribute names**

The rest of this plan assumes `upstox_client.Configuration()` has a settable `.access_token` attribute and `upstox_client.ApiClient(configuration)` takes that `Configuration` as its constructor argument — the standard shape for this Swagger-codegen-style SDK, matching how `backend/app/market_data/upstox_v3.py` already imports `ApiClient` from it. Confirm this now that the package is installed:

```bash
cd D:/sanate && .venv/Scripts/python.exe -c "
import upstox_client
c = upstox_client.Configuration()
c.access_token = 'test'
client = upstox_client.ApiClient(c)
print('OK', type(client))
"
```

Expected: prints `OK <class 'upstox_client.api_client.ApiClient'>` with no error. If the attribute or constructor shape differs, note the real shape now — Task 3's `configure()` implementation must match it exactly.

- [ ] **Step 7: Add env config files**

Create `backend/.env.example`:

```
UPSTOX_API_KEY=
UPSTOX_API_SECRET=
UPSTOX_REDIRECT_URI=http://localhost:8000/api/v1/broker/upstox/callback
```

Copy it to a real `backend/.env` and fill in your actual Upstox app credentials (this file is gitignored — never commit it):

```bash
cd D:/sanate && cp backend/.env.example backend/.env
```

Then edit `backend/.env` to fill in `UPSTOX_API_KEY` and `UPSTOX_API_SECRET` from your Upstox developer app.

- [ ] **Step 8: Gitignore the token file**

In `.gitignore`, in the "Environment / secrets" block (currently lines 88-95), add a line after `!.env.example`:

```
.env
.env.*
!.env.example
backend/.token.json
*.local
```

- [ ] **Step 9: Commit**

```bash
cd D:/sanate && git add backend/app/market_data/symbols.py backend/tests/test_symbols.py backend/requirements.txt backend/.env.example .gitignore
git commit -m "feat: add index instrument keys and Upstox env/SDK config"
```

---

## Task 2: Token persistence (save/load)

**Files:**
- Create: `backend/app/core/upstox_auth.py`
- Create: `backend/tests/test_upstox_auth.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `TOKEN_PATH: pathlib.Path`, `save_token(access_token: str) -> None`, `load_token() -> str | None`. Task 5 (broker.py) and Task 6 (main.py) call `save_token`/`load_token`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_upstox_auth.py`:

```python
import json

from backend.app.core import upstox_auth


def test_load_token_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(upstox_auth, "TOKEN_PATH", tmp_path / ".token.json")
    assert upstox_auth.load_token() is None


def test_save_then_load_token_roundtrip(tmp_path, monkeypatch):
    token_path = tmp_path / ".token.json"
    monkeypatch.setattr(upstox_auth, "TOKEN_PATH", token_path)

    upstox_auth.save_token("abc123")

    assert token_path.exists()
    saved = json.loads(token_path.read_text())
    assert saved["access_token"] == "abc123"
    assert "obtained_at" in saved

    assert upstox_auth.load_token() == "abc123"


def test_load_token_returns_none_for_malformed_file(tmp_path, monkeypatch):
    token_path = tmp_path / ".token.json"
    token_path.write_text("not valid json")
    monkeypatch.setattr(upstox_auth, "TOKEN_PATH", token_path)

    assert upstox_auth.load_token() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_upstox_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.core.upstox_auth'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/core/upstox_auth.py`:

```python
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

TOKEN_PATH = Path(__file__).resolve().parent.parent.parent / ".token.json"


class UpstoxAuthError(Exception):
    """Raised when the Upstox OAuth flow fails."""


def save_token(access_token: str) -> None:
    TOKEN_PATH.write_text(
        json.dumps(
            {
                "access_token": access_token,
                "obtained_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )


def load_token() -> Optional[str]:
    if not TOKEN_PATH.exists():
        return None
    try:
        data = json.loads(TOKEN_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return data.get("access_token")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_upstox_auth.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd D:/sanate && git add backend/app/core/upstox_auth.py backend/tests/test_upstox_auth.py
git commit -m "feat: add local Upstox token persistence"
```

---

## Task 3: Authorization URL + token exchange

**Files:**
- Modify: `backend/app/core/upstox_auth.py`
- Modify: `backend/tests/test_upstox_auth.py`

**Interfaces:**
- Consumes: `UpstoxAuthError` (Task 2, same file).
- Produces: `get_authorization_url() -> str`, `async exchange_code_for_token(code: str) -> str` (raises `UpstoxAuthError` on failure). Task 5 (broker.py) calls both.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_upstox_auth.py`:

```python
import httpx
import pytest

from backend.app.core.upstox_auth import UpstoxAuthError


def test_get_authorization_url_uses_env_vars(monkeypatch):
    monkeypatch.setenv("UPSTOX_API_KEY", "my-client-id")
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")

    url = upstox_auth.get_authorization_url()

    assert url.startswith("https://api.upstox.com/v2/login/authorization/dialog?")
    assert "client_id=my-client-id" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fcallback" in url
    assert "response_type=code" in url


@pytest.mark.asyncio
async def test_exchange_code_for_token_success(monkeypatch):
    monkeypatch.setenv("UPSTOX_API_KEY", "my-client-id")
    monkeypatch.setenv("UPSTOX_API_SECRET", "my-secret")
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")

    def handler(request):
        assert request.url.path == "/v2/login/authorization/token"
        return httpx.Response(200, json={"access_token": "live-token-xyz"})

    transport = httpx.MockTransport(handler)

    monkeypatch.setattr(
        upstox_auth.httpx, "AsyncClient", lambda *a, **kw: httpx.AsyncClient(transport=transport)
    )

    token = await upstox_auth.exchange_code_for_token("auth-code-123")

    assert token == "live-token-xyz"


@pytest.mark.asyncio
async def test_exchange_code_for_token_failure_raises(monkeypatch):
    monkeypatch.setenv("UPSTOX_API_KEY", "my-client-id")
    monkeypatch.setenv("UPSTOX_API_SECRET", "my-secret")
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")

    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        upstox_auth.httpx, "AsyncClient", lambda *a, **kw: httpx.AsyncClient(transport=transport)
    )

    with pytest.raises(UpstoxAuthError):
        await upstox_auth.exchange_code_for_token("bad-code")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_upstox_auth.py -v`
Expected: FAIL — `AttributeError: module 'backend.app.core.upstox_auth' has no attribute 'get_authorization_url'`

- [ ] **Step 3: Write minimal implementation**

In `backend/app/core/upstox_auth.py`, add near the top (after the `logger = ...` line) and at the bottom of the file:

```python
import os
from urllib.parse import urlencode

import httpx
```

(add these three imports to the existing `import` block at the top of the file)

Then append to the bottom of the file:

```python
AUTHORIZE_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"


def get_authorization_url() -> str:
    params = {
        "client_id": os.environ["UPSTOX_API_KEY"],
        "redirect_uri": os.environ["UPSTOX_REDIRECT_URI"],
        "response_type": "code",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": os.environ["UPSTOX_API_KEY"],
                "client_secret": os.environ["UPSTOX_API_SECRET"],
                "redirect_uri": os.environ["UPSTOX_REDIRECT_URI"],
                "grant_type": "authorization_code",
            },
            headers={
                "accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

    if response.status_code != 200:
        raise UpstoxAuthError(
            f"Token exchange failed ({response.status_code}): {response.text}"
        )

    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        raise UpstoxAuthError(f"Token exchange response missing access_token: {data}")

    return access_token
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_upstox_auth.py -v`
Expected: PASS (6 tests total)

- [ ] **Step 5: Commit**

```bash
cd D:/sanate && git add backend/app/core/upstox_auth.py backend/tests/test_upstox_auth.py
git commit -m "feat: add real Upstox authorization URL and token exchange"
```

---

## Task 4: `UpstoxV3Client.configure()`

**Files:**
- Modify: `backend/app/market_data/upstox_v3.py`
- Modify: `backend/tests/test_upstox_v3.py`

**Interfaces:**
- Consumes: `INDEX_INSTRUMENT_KEYS` (Task 1, `backend/app/market_data/symbols.py`).
- Produces: `UpstoxV3Client.configure(access_token: str) -> None` (rebuilds `self.streamer` from a live `ApiClient`/`MarketDataStreamerV3`, keeping `self.subscriptions`), and moves the module-level singleton `upstox_client` into this file: `upstox_client = UpstoxV3Client(instrument_keys=list(INDEX_INSTRUMENT_KEYS.values()))`. Task 5 (`broker.py`) and Task 6 (`main.py`) import `upstox_client` from here instead of constructing/importing it in `main.py`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_upstox_v3.py`:

```python
import backend.app.market_data.upstox_v3 as upstox_v3_module


def test_configure_builds_live_streamer(monkeypatch):
    mock_streamer_instance = MagicMock()
    mock_streamer_cls = MagicMock(return_value=mock_streamer_instance)
    mock_api_client_cls = MagicMock()
    mock_configuration_cls = MagicMock()

    monkeypatch.setattr(upstox_v3_module, "UPSTOX_AVAILABLE", True)
    monkeypatch.setattr(upstox_v3_module, "MarketDataStreamerV3", mock_streamer_cls)
    monkeypatch.setattr(upstox_v3_module, "ApiClient", mock_api_client_cls)
    monkeypatch.setattr(upstox_v3_module, "Configuration", mock_configuration_cls)

    client = upstox_v3_module.UpstoxV3Client(instrument_keys=["NSE_INDEX|Nifty 50"])
    assert client.streamer is None  # still mock mode before configure()

    client.configure("real-token-123")

    assert client.streamer is mock_streamer_instance
    mock_streamer_cls.assert_called_once_with(mock_api_client_cls.return_value, ["NSE_INDEX|Nifty 50"])
    assert mock_streamer_instance.on.call_count == 4


def test_configure_closes_existing_streamer_first(monkeypatch):
    old_streamer = MagicMock()
    new_streamer = MagicMock()
    mock_streamer_cls = MagicMock(return_value=new_streamer)

    monkeypatch.setattr(upstox_v3_module, "UPSTOX_AVAILABLE", True)
    monkeypatch.setattr(upstox_v3_module, "MarketDataStreamerV3", mock_streamer_cls)
    monkeypatch.setattr(upstox_v3_module, "ApiClient", MagicMock())
    monkeypatch.setattr(upstox_v3_module, "Configuration", MagicMock())

    client = upstox_v3_module.UpstoxV3Client(instrument_keys=["NSE_INDEX|Nifty 50"])
    client.streamer = old_streamer

    client.configure("real-token-123")

    old_streamer.close.assert_called_once()
    assert client.streamer is new_streamer


def test_singleton_upstox_client_has_index_subscriptions():
    from backend.app.market_data.symbols import INDEX_INSTRUMENT_KEYS

    assert upstox_v3_module.upstox_client.subscriptions == set(INDEX_INSTRUMENT_KEYS.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_upstox_v3.py -v`
Expected: FAIL — `AttributeError: 'UpstoxV3Client' object has no attribute 'configure'`

- [ ] **Step 3: Write minimal implementation**

Replace the whole contents of `backend/app/market_data/upstox_v3.py` with:

```python
import asyncio
import logging
import json
import ssl
from typing import Dict, Any, Callable
from datetime import datetime

try:
    from upstox_client.api_client import ApiClient
    from upstox_client.configuration import Configuration
    from upstox_client.feeder.market_data_streamer_v3 import MarketDataStreamerV3
    UPSTOX_AVAILABLE = True
except ImportError:
    UPSTOX_AVAILABLE = False
    ApiClient = None
    Configuration = None
    MarketDataStreamerV3 = None

from .models import Tick
from .symbols import INDEX_INSTRUMENT_KEYS
from backend.app.core.event_bus import event_bus

logger = logging.getLogger(__name__)

class UpstoxV3Client:
    def __init__(self, api_client: ApiClient = None, instrument_keys=None):
        self.api_client = api_client
        self.subscriptions = set(instrument_keys) if instrument_keys else set()
        if UPSTOX_AVAILABLE and api_client:
            self.streamer = MarketDataStreamerV3(self.api_client, instrument_keys or [])
            self._wire_handlers()
        else:
            self.streamer = None

    def _wire_handlers(self):
        self.streamer.on("message", self._on_message)
        self.streamer.on("open", self._on_open)
        self.streamer.on("close", self._on_close)
        self.streamer.on("error", self._on_error)

    def configure(self, access_token: str) -> None:
        """Switch from mock mode into a real live-feed client using a real
        OAuth access token. Safe to call again later (e.g. after a fresh
        login replaces an expired token) — closes any existing streamer
        first."""
        if not UPSTOX_AVAILABLE:
            logger.warning(
                "upstox_client SDK not installed; cannot configure a live feed"
            )
            return

        if self.streamer:
            try:
                self.streamer.close()
            except Exception:
                pass

        configuration = Configuration()
        configuration.access_token = access_token
        self.api_client = ApiClient(configuration)
        self.streamer = MarketDataStreamerV3(
            self.api_client, list(self.subscriptions)
        )
        self._wire_handlers()

    async def connect(self):
        if self.streamer:
            # MarketDataStreamerV3 handles auto-reconnect typically, but we call connect
            self.streamer.connect()
        else:
            logger.warning("UpstoxV3Client missing api_client, running in mock mode")

    def _on_open(self):
        logger.info("Connected to Upstox V3 Market Data Feed")

    def _on_close(self, code, reason):
        logger.warning(f"Upstox V3 Connection closed: {code} - {reason}")

    def _on_error(self, error):
        logger.error(f"Upstox V3 Error: {error}")

    def _on_message(self, message):
        try:
            # Process protobuf decoded message (streamer library does this automatically)
            # The message format is a dictionary representing the protobuf schema
            # Assuming message contains feeds dictionary: { 'NSE_EQ|INE123': {'ff': {'marketFF': {'ltpc': {'ltp': 100}}}} }
            if "feeds" in message:
                for instrument_key, feed in message["feeds"].items():
                    asyncio.create_task(self._publish_tick(instrument_key, feed))
        except Exception as e:
            logger.error(f"Error processing V3 message: {e}")

    async def _publish_tick(self, instrument_key: str, data: dict):
        try:
            # Try to get data from Full Feed (ff) or Option Feed (of)
            ff = data.get("ff", {})
            marketFF = ff.get("marketFF", {})
            ltpc = marketFF.get("ltpc", {})

            # If full_d30 format
            ltp = ltpc.get("ltp")
            volume = marketFF.get("v", 0)

            if ltp is None:
                # Try finding LTP elsewhere in the dict if the schema is different
                return

            tick = Tick(
                instrument=instrument_key,
                price=float(ltp),
                volume=float(volume),
                timestamp=datetime.now(),
                is_trade=True
            )
            # Note: The protobuf decode by streamer usually outputs fields exactly as named in the proto
            await event_bus.publish("MARKET_TICK", tick)

        except Exception as e:
            logger.error(f"Error publishing tick: {e}")

    async def close(self):
        if self.streamer:
            self.streamer.close()


# Module-level singleton — lives here (not main.py) so broker.py can import
# it without a circular import (main.py imports broker.py's router).
upstox_client = UpstoxV3Client(instrument_keys=list(INDEX_INSTRUMENT_KEYS.values()))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_upstox_v3.py -v`
Expected: PASS (4 tests total)

- [ ] **Step 5: Commit**

```bash
cd D:/sanate && git add backend/app/market_data/upstox_v3.py backend/tests/test_upstox_v3.py
git commit -m "feat: add UpstoxV3Client.configure() and move singleton into upstox_v3.py"
```

---

## Task 5: Wire `broker.py` to real OAuth

**Files:**
- Modify: `backend/app/api/endpoints/broker.py` (full rewrite)
- Create: `backend/tests/test_broker.py`

**Interfaces:**
- Consumes: `upstox_auth.get_authorization_url()`, `upstox_auth.exchange_code_for_token()`, `upstox_auth.save_token()`, `upstox_auth.UpstoxAuthError` (Task 2/3); `upstox_client` singleton with `.configure()` and `.connect()` (Task 4).
- Produces: same two routes (`GET /api/v1/broker/upstox/login`, `GET /api/v1/broker/upstox/callback`), now backed by real calls.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_broker.py`:

```python
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.endpoints.broker import router as broker_router

app = FastAPI()
app.include_router(broker_router)
client = TestClient(app)


def test_login_redirects_to_real_upstox_url(monkeypatch):
    monkeypatch.setenv("UPSTOX_API_KEY", "my-client-id")
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/api/v1/broker/upstox/callback")

    response = client.get("/api/v1/broker/upstox/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    location = response.headers["location"]
    assert location.startswith("https://api.upstox.com/v2/login/authorization/dialog?")
    assert "client_id=my-client-id" in location


def test_callback_success_saves_token_and_configures_client():
    with patch(
        "backend.app.api.endpoints.broker.upstox_auth.exchange_code_for_token",
        new=AsyncMock(return_value="live-token-xyz"),
    ) as mock_exchange, patch(
        "backend.app.api.endpoints.broker.upstox_auth.save_token"
    ) as mock_save, patch(
        "backend.app.api.endpoints.broker.upstox_client"
    ) as mock_client:
        mock_client.connect = AsyncMock()

        response = client.get(
            "/api/v1/broker/upstox/callback?code=auth-code-123&state=xyz"
        )

        assert response.status_code == 200
        assert "Upstox Connected" in response.text
        mock_exchange.assert_awaited_once_with("auth-code-123")
        mock_save.assert_called_once_with("live-token-xyz")
        mock_client.configure.assert_called_once_with("live-token-xyz")
        mock_client.connect.assert_awaited_once()


def test_callback_failure_renders_error_page():
    from backend.app.core.upstox_auth import UpstoxAuthError

    with patch(
        "backend.app.api.endpoints.broker.upstox_auth.exchange_code_for_token",
        new=AsyncMock(side_effect=UpstoxAuthError("invalid_grant")),
    ):
        response = client.get(
            "/api/v1/broker/upstox/callback?code=bad-code&state=xyz"
        )

        assert response.status_code == 502
        assert "Upstox Connection Failed" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_broker.py -v`
Expected: FAIL — first test fails because `/login` still returns the old mock `RedirectResponse` to `/callback` instead of a real Upstox URL (a `KeyError` on `UPSTOX_API_KEY` won't happen yet since the old code never reads it).

- [ ] **Step 3: Write minimal implementation**

Replace the whole contents of `backend/app/api/endpoints/broker.py` with:

```python
import logging
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.app.core import upstox_auth
from backend.app.market_data.upstox_v3 import upstox_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/broker/upstox", tags=["broker"])


def _result_page(status: str, detail: str = "") -> str:
    is_error = status == "ERROR"
    heading = "Upstox Connection Failed" if is_error else "Upstox Connected"
    color = "#ef4444" if is_error else "#10b981"
    body_text = detail or "Authentication successful. You can close this window."
    close_delay_ms = "3000" if is_error else "1000"

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{heading}</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background: #09090b; color: {color}; margin: 0; }}
            .container {{ text-align: center; border: 1px solid #27272a; padding: 2rem; border-radius: 8px; background: #18181b; max-width: 480px; }}
            h1 {{ margin-bottom: 1rem; font-size: 1.5rem; text-transform: uppercase; letter-spacing: 0.05em; }}
            p {{ color: #a1a1aa; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{heading}</h1>
            <p>{body_text}</p>
        </div>
        <script>
            if (window.opener) {{
                const message = {{
                    type: "BROKER_AUTH_COMPLETE",
                    broker: "UPSTOX",
                    status: "{status}"
                }};
                window.opener.postMessage(message, window.location.origin);
            }} else {{
                console.warn("No opener window found.");
            }}
            setTimeout(() => {{ window.close(); }}, {close_delay_ms});
        </script>
    </body>
    </html>
    """


@router.get("/login")
async def upstox_login():
    return RedirectResponse(url=upstox_auth.get_authorization_url())


@router.get("/callback")
async def upstox_callback(code: str = Query(...), state: str = Query(None)):
    logger.info("Received Upstox callback")

    try:
        token = await upstox_auth.exchange_code_for_token(code)
    except upstox_auth.UpstoxAuthError as exc:
        logger.error(f"Upstox token exchange failed: {exc}")
        return HTMLResponse(content=_result_page("ERROR", str(exc)), status_code=502)

    upstox_auth.save_token(token)
    upstox_client.configure(token)
    await upstox_client.connect()

    return HTMLResponse(content=_result_page("CONNECTED"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_broker.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd D:/sanate && git add backend/app/api/endpoints/broker.py backend/tests/test_broker.py
git commit -m "feat: wire broker.py login/callback to real Upstox OAuth"
```

---

## Task 6: Load saved token on startup

**Files:**
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `upstox_auth.load_token()` (Task 2), `upstox_client` singleton now imported from `upstox_v3.py` (Task 4).
- Produces: nothing new consumed by later tasks — this is the final wiring point.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_main_upstox_startup.py`:

```python
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def test_startup_configures_client_when_token_exists():
    with patch(
        "backend.app.main.upstox_auth.load_token", return_value="saved-token-abc"
    ), patch("backend.app.main.upstox_client") as mock_client:
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()

        from backend.app.main import app

        with TestClient(app):
            pass

        mock_client.configure.assert_called_once_with("saved-token-abc")


def test_startup_skips_configure_when_no_token():
    with patch(
        "backend.app.main.upstox_auth.load_token", return_value=None
    ), patch("backend.app.main.upstox_client") as mock_client:
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()

        from backend.app.main import app

        with TestClient(app):
            pass

        mock_client.configure.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_main_upstox_startup.py -v --timeout=60`
Expected: FAIL — `mock_client.configure.assert_called_once_with(...)` fails because `main.py` doesn't call `load_token()`/`configure()` yet (and `backend.app.main.upstox_client` doesn't exist as a patchable name until this task's Step 3 changes the import).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/main.py`:

1. Replace this line:

```python
from backend.app.market_data.upstox_v3 import UpstoxV3Client

# Mock or global instance
upstox_client = UpstoxV3Client()
```

with:

```python
from backend.app.market_data.upstox_v3 import upstox_client
from backend.app.core import upstox_auth
```

2. Replace this line inside `lifespan()`:

```python
    # Start Upstox stream
    asyncio.create_task(upstox_client.connect())
```

with:

```python
    # Start Upstox stream — use a saved token if we have one, otherwise
    # this stays in the existing mock-mode (logs a warning, no crash).
    saved_token = upstox_auth.load_token()
    if saved_token:
        upstox_client.configure(saved_token)
    asyncio.create_task(upstox_client.connect())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_main_upstox_startup.py -v --timeout=60`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full backend suite**

Run: `python -m pytest -q --timeout=60`
Expected: same baseline as before this feature — 112 passed plus this task's new tests, plus the 3 pre-existing unrelated failures (`test_bullish_setup`, `test_full_event_flow`, `test_candle_aggregation_no_look_ahead`) which this plan does not touch. No hangs, no new failures.

- [ ] **Step 6: Commit**

```bash
cd D:/sanate && git add backend/app/main.py backend/tests/test_main_upstox_startup.py
git commit -m "feat: load saved Upstox token on startup"
```

---

## Task 7: Manual end-to-end verification

This task has no automated test — it's a real login against the real Upstox API, which cannot be safely automated (it needs your live credentials and a human completing the OAuth consent screen).

- [ ] **Step 1: Start the backend for real**

```bash
cd D:/sanate && PYTHONPATH=. .venv/Scripts/python.exe -m uvicorn backend.app.main:app --port 8000
```

Confirm the startup log shows either `UpstoxV3Client missing api_client, running in mock mode` (no saved token yet — expected on a first run) with no crash.

- [ ] **Step 2: Run the real login flow**

Open `http://localhost:8000/api/v1/broker/upstox/login` in a browser. Confirm it redirects to Upstox's real login/consent page (`api.upstox.com`). Log in with your Upstox Plus account and approve.

- [ ] **Step 3: Confirm the callback succeeded**

Confirm you land back on the "Upstox Connected" page (green, from `_result_page`) rather than "Upstox Connection Failed". Check the server log for `Connected to Upstox V3 Market Data Feed` (the `_on_open` handler).

- [ ] **Step 4: Confirm live ticks are flowing**

Check the server log for no repeated `Upstox V3 Error` lines. If your frontend has a live price display wired to `MARKET_TICK` events, confirm NIFTY/BANKNIFTY/SENSEX prices update in real time during market hours. Outside market hours, absence of errors and a stable "Connected" state is sufficient confirmation.

- [ ] **Step 5: Confirm the token survives a restart**

Stop the server (Ctrl+C) and start it again with the same command from Step 1. Confirm the startup log this time shows `Connected to Upstox V3 Market Data Feed` without needing to visit `/login` again — i.e. `backend/.token.json` was picked up on startup.

- [ ] **Step 6: Confirm `backend/.token.json` is not tracked by git**

```bash
cd D:/sanate && git status --short backend/.token.json
```

Expected: no output (the file exists on disk but git ignores it, per Task 1 Step 8).
