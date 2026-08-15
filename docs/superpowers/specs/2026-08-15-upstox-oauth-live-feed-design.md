# Upstox OAuth + Live Spot Feed — Design

## Context

`backend/app/market_data/upstox_v3.py`'s `UpstoxV3Client` currently only runs in
"mock mode": it's instantiated with `api_client=None` at import time in
`backend/app/main.py`, so `connect()` just logs a warning and no live data ever
flows. `backend/app/api/endpoints/broker.py`'s `/login` and `/callback`
endpoints are pure UI-flow stubs — `/login` redirects straight to `/callback`
with a hardcoded `mock_auth_code_12345`, and no code ever calls Upstox's real
OAuth or WebSocket APIs. There is no token storage, no Upstox API credentials
config, and no `upstox_client` SDK installed.

The user has an active Upstox Plus subscription and wants this wired to the
real API: a real OAuth login flow, and a real live market-data feed for index
spot prices.

## Goal

Wire the existing OAuth stub and `UpstoxV3Client` to Upstox's real APIs so
that:

1. `/login` sends the user through Upstox's actual authorization dialog.
2. `/callback` exchanges the returned code for a real access token and
   persists it locally.
3. The live V3 market-data WebSocket feed streams real LTP/volume ticks for
   NIFTY, BANKNIFTY, and SENSEX index spot prices onto the existing
   `MARKET_TICK` event-bus topic — the same topic `UpstoxV3Client._publish_tick`
   already publishes to today, so no downstream consumer needs to change.

## Explicit non-goals

- **No option-chain / per-strike subscription.** Only the three index spot
  instrument keys are subscribed. Fetching each expiry's contract list and
  subscribing per-strike (for OI/greeks) is a separate, larger follow-up
  project.
- **No refresh-token flow.** Upstox's API does not support refresh tokens;
  access tokens expire daily and require a fresh login through `/login`. This
  design does not add auto-refresh, scheduled re-login prompts, or a
  background health-check poller — just clear logging when the feed's auth
  fails, telling the operator to re-login.
- **No encrypted token storage.** The token file is a plain local JSON file,
  consistent with this being a solo local-dev tool with no multi-user or
  hosted-deployment concerns in scope.

## Components

### `backend/app/market_data/symbols.py` (new)

Single source of truth for the three index instrument keys:

```python
INDEX_INSTRUMENT_KEYS = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "SENSEX": "BSE_INDEX|SENSEX",
}
```

### `backend/app/core/upstox_auth.py` (new)

Owns everything OAuth and token persistence:

- `get_authorization_url() -> str` — builds
  `https://api.upstox.com/v2/login/authorization/dialog?...` from
  `UPSTOX_API_KEY` / `UPSTOX_REDIRECT_URI` env vars.
- `async exchange_code_for_token(code: str) -> str` — POSTs to
  `https://api.upstox.com/v2/login/authorization/token` with
  `client_id`/`client_secret`/`redirect_uri`/`grant_type=authorization_code`
  via `httpx.AsyncClient`; returns the `access_token` string. Raises a plain
  exception with the response body on failure (caller turns this into an HTTP
  error page).
- `save_token(access_token: str) -> None` — writes
  `{"access_token": ..., "obtained_at": "<ISO8601 UTC>"}` to
  `backend/.token.json`.
- `load_token() -> Optional[str]` — reads the file if present and returns the
  `access_token`, or `None` if the file doesn't exist or is malformed. No
  expiry check here (Upstox tokens are always valid until ~3:30am IST the
  next day; we don't try to predict that — an actual API/feed 401 is the
  signal that it's stale).

Both `save_token`/`load_token` take the file path from a module-level
`TOKEN_PATH` constant resolved relative to this module's own file location
(`Path(__file__).resolve().parent.parent.parent / ".token.json"`, i.e.
`backend/.token.json`) rather than the current working directory — the repo
already has one CWD inconsistency (`README.md`'s documented `uvicorn
app.main:app` command doesn't match `main.py`'s `backend.app...`-prefixed
imports, which only resolve when run from the repo root), so token lookup
should not add a second thing that silently breaks depending on where the
process is launched from. Tests monkeypatch `TOKEN_PATH` directly.

### `UpstoxV3Client` changes (`backend/app/market_data/upstox_v3.py`)

Add a `configure(access_token: str) -> None` method:

- Builds `upstox_client.Configuration()` + `ApiClient` with the token.
- If an existing `self.streamer` is already connected, closes it first.
- Creates a new `MarketDataStreamerV3(api_client, list(INDEX_INSTRUMENT_KEYS.values()))`,
  re-registers the same `on("message"/"open"/"close"/"error", ...)` handlers
  that `__init__` already wires up (refactor that wiring into a small
  `_wire_handlers()` helper shared by `__init__` and `configure`), and stores
  it as `self.streamer`.
- Does **not** call `.connect()` itself — the caller (`main.py` startup or the
  `/callback` handler) decides when to connect, matching the existing
  `connect()` contract.

This lets the module-level singleton `upstox_client` (already referenced by
`main.py`'s lifespan and closed on shutdown) flip from mock mode into a real
streamer without any consumer needing a new reference.

### `broker.py` changes

- `/login`: redirect to `upstox_auth.get_authorization_url()` instead of the
  mock self-callback.
- `/callback`: on success, `await upstox_auth.exchange_code_for_token(code)`,
  `upstox_auth.save_token(token)`, then `upstox_client.configure(token)` +
  `await upstox_client.connect()` so the feed goes live immediately without a
  restart. On failure, render a plain error HTML page (reusing the existing
  postMessage pattern but with `status: "ERROR"`) instead of the success page.

### `main.py` changes

In `lifespan`, before `asyncio.create_task(upstox_client.connect())`: try
`upstox_auth.load_token()`; if a token is present, call
`upstox_client.configure(token)` first. If absent, behavior is unchanged
(mock mode, existing warning log).

### Config

- `backend/requirements.txt`: add `upstox-python-sdk`, `python-dotenv`.
- `backend/.env.example` (new, since none exists yet): add
  `UPSTOX_API_KEY=`, `UPSTOX_API_SECRET=`, `UPSTOX_REDIRECT_URI=http://localhost:8000/api/v1/broker/upstox/callback`.
- `backend/app/main.py` (or a tiny bootstrap at the top) calls
  `dotenv.load_dotenv()` early so `backend/.env` is picked up the same way
  `DUCKDB_PATH` etc. are read via `os.getenv`.
- `.gitignore`: add `backend/.token.json`.

## Error handling

- Token exchange HTTP failure → `/callback` renders an error page (browser
  console/UI already listens for `postMessage`; error status flows through
  the same channel the success path uses) instead of silently redirecting.
- Live feed auth failure (401 from the WebSocket feed after a token goes
  stale) → `_on_error` handler logs "Upstox token expired — re-login via
  /api/v1/broker/upstox/login" at ERROR level. The app keeps running; no
  crash, no retry loop. (Today's `_on_error` just logs; this design keeps
  that shape and only improves the log message for this specific case if
  the SDK exposes an identifiable auth-failure code — otherwise the existing
  generic log line is left as-is rather than guessing at SDK error shapes.)
- `configure()` never raises for a missing token — that's `load_token()`
  returning `None`, which the caller checks before calling `configure()` at
  all.

## Testing

- `backend/tests/test_upstox_auth.py` (new):
  - `get_authorization_url()` builds the expected URL from env vars
    (monkeypatched).
  - `exchange_code_for_token()` against a mocked `httpx.AsyncClient` response
    — both success (returns token) and failure (raises) paths.
  - `save_token()` / `load_token()` roundtrip using `tmp_path` for
    `TOKEN_PATH`, plus `load_token()` returning `None` for a missing file.
- `backend/tests/test_upstox_v3.py` (existing, extended): a new test for
  `configure()` — asserts `self.streamer` is created with the right
  instrument keys and handlers wired, using a fake/mocked `ApiClient` (no
  real network call). The existing mock-mode test is untouched.
- `backend/tests/test_broker.py` (new): `/login` redirects to a URL
  containing the configured `client_id`/`redirect_uri`; `/callback` with a
  mocked `exchange_code_for_token` saves a token and returns the success
  page; a mocked-failure case returns the error page.

No test makes a real network call to Upstox — everything is mocked at the
`httpx`/SDK boundary.
