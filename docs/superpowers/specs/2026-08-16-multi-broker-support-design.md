# Multi-Broker Support (Upstox / Dhan / Zerodha) — Design

## Problem

The platform already lets a user save credentials and complete a real login/token
flow for three brokers (Upstox, Zerodha, Dhan) — `credential_store.py` and
`broker_registry.py` are broker-agnostic, and `upstox_auth.py` / `zerodha_auth.py`
/ `dhan_auth.py` each expose a working connect flow.

Everything downstream of "connected," however, is hardwired to Upstox:

- The live tick feed (`market_data/upstox_v3.py`, started unconditionally in
  `main.py`).
- Option chain, market quote, and historical-candle fetches
  (`market_data/option_chain_client.py`, `market_data/market_quote.py`,
  `market_data/historical_candles.py`) — all call Upstox REST endpoints
  directly.
- The underlying→instrument-key mapping (`market_data/symbols.py`).
- Real order placement (`execution/order_gateway.py`) — hardcodes Upstox's
  live/sandbox URLs and `upstox_auth.load_token()`.

Roughly 30 files across strategies, execution, and market data import one of
these Upstox modules directly.

## Goal

The user runs this as a personal, single-operator platform and wants a
SaaS-style broker picker: **whichever broker is connected and selected as
active drives data feed and order execution for the whole system** — like
Zerodha being active means all data and all order execution use Zerodha, and
nothing else.

## Scope and phasing

This is being delivered in three phases, each independently shippable and
tested:

1. **Phase 1 (this spec's primary deliverable): broker-agnostic plumbing.**
   Introduce `MarketDataProvider` and `BrokerExecutionAdapter` interfaces, an
   active-broker switch, and refactor Upstox onto both interfaces with
   **no behavior change** — a pure proof that the abstraction is sound,
   validated by the existing test suite staying green.
2. **Phase 2: Dhan.** Real `MarketDataProvider` + `BrokerExecutionAdapter`
   implementations for Dhan, built to Dhan's documented API. No live
   credentials available during development — verified with mocked
   HTTP/websocket responses; real-world verification happens once the user
   has it connected.
3. **Phase 3: Zerodha (Kite Connect).** Same approach as Phase 2, for
   Zerodha. The user does not currently have an active Kite Connect
   subscription, so this is also built to spec and mock-tested, not
   live-verified during development.

Each phase gets its own implementation plan via `writing-plans`, entered only
after the prior phase is complete and reviewed. This document specs Phase 1
in full and describes Phases 2/3 at the level needed to confirm Phase 1's
interfaces will actually fit them.

## Architecture

Two provider interfaces, one active-broker switch:

- **`MarketDataProvider`** (`backend/app/market_data/provider.py`) — a
  `Protocol` covering:
  - `instrument_key_for_index(underlying: str) -> str`
  - `async connect_feed() -> None` / `async disconnect_feed() -> None` —
    starts/stops a live tick websocket that publishes the existing
    broker-neutral `Tick` model (`market_data/models.py`) onto the
    `MARKET_TICK` event-bus channel, exactly as `upstox_v3.py` does today.
  - `async fetch_option_chain(index_key, token, expiry) -> List[Dict]` —
    returns the same canonical dict shape Upstox's endpoint returns today
    (`call_options`/`put_options`/`market_data`/`option_greeks` per strike),
    since ~15 strategy files already parse that exact shape. Dhan/Zerodha
    implementations translate their native responses into this shape at the
    boundary rather than strategies learning three different shapes.
  - `async fetch_quote(instrument_key, token) -> Quote` — reuses the
    existing broker-neutral `Quote` dataclass from `market_quote.py`.
  - `async fetch_historical_candles(instrument_key, token, to_date,
    from_date, interval) -> List[Dict]` — reuses the existing canonical row
    shape from `historical_candles.py`.

- **`BrokerExecutionAdapter`** (`backend/app/execution/broker_adapter.py`) —
  a `Protocol` with one method: `async place_order(request: OrderRequest,
  mode: ExecutionMode) -> OrderResult`, reusing the existing broker-neutral
  `OrderRequest`/`OrderResult` dataclasses from `order_gateway.py`.
  `order_gateway.py`'s `OrderGateway.place_order` becomes a thin dispatcher:
  DRY_RUN short-circuit stays exactly as-is (broker-agnostic, no network
  call regardless of active broker); for SANDBOX/LIVE it resolves the active
  broker's adapter and delegates.

- **Active-broker state** (`backend/app/core/active_broker.py`) — persisted
  similarly to `credential_store.py` (a small gitignored JSON file), holding
  the currently active broker id (or none). Exposes:
  - `get_active_broker_id() -> Optional[str]`
  - `get_active_provider() -> MarketDataProvider`
  - `get_active_execution_adapter() -> BrokerExecutionAdapter`
  - `get_active_auth_module()` — returns whichever of `upstox_auth` /
    `zerodha_auth` / `dhan_auth` is active (all three already expose a
    uniform `load_token()`).
  - `async set_active_broker(broker_id: str) -> None` — the only way the
    active broker changes; see Data Flow below for what this does.

Because `Tick`, `OrderRequest`/`OrderResult`, `Quote`, and the option-chain
dict shape are already broker-neutral and consumed by strategy code as such,
**no strategy file's logic changes** — only its imports move from a specific
Upstox module to `active_broker.get_active_provider()` /
`get_active_execution_adapter()`.

## Components

- `backend/app/core/active_broker.py` — new. Active-broker state + lookups
  described above.
- `backend/app/market_data/provider.py` — new. `MarketDataProvider` protocol.
- `backend/app/market_data/upstox_provider.py` — new. Wraps the existing
  `upstox_v3.py` / `option_chain_client.py` / `market_quote.py` /
  `historical_candles.py` / `symbols.py` logic behind the protocol. No
  behavior change — existing modules are not deleted, just wrapped (later
  phases may inline them once nothing else references the raw modules
  directly).
- `backend/app/execution/broker_adapter.py` — new. `BrokerExecutionAdapter`
  protocol.
- `backend/app/execution/upstox_adapter.py` — new. Wraps the order-placement
  logic currently inline in `order_gateway.py` (URL selection, payload,
  headers, response parsing) — moved, not rewritten.
- `backend/app/execution/order_gateway.py` — modified. `place_order` keeps
  its DRY_RUN branch and the full two-factor LIVE arm/env-var check
  (`resolve_mode()`), then delegates to
  `active_broker.get_active_execution_adapter().place_order(...)` for
  SANDBOX/LIVE.
- `backend/app/main.py` — modified. Startup no longer unconditionally
  connects `upstox_client`; it calls
  `active_broker.get_active_provider().connect_feed()` if a broker is both
  connected and active, otherwise starts with no live feed.
- ~30 existing call sites (strategies, execution, market data) — modified to
  call through `active_broker.get_active_provider()` /
  `get_active_execution_adapter()` instead of importing an Upstox module
  directly. Mechanical redirect, no logic change.
- `backend/app/api/endpoints/brokers.py` — modified. Adds:
  - `GET /api/v1/brokers/active` — returns the current active broker id (or
    null).
  - `POST /api/v1/brokers/active` `{broker_id}` — validates the broker is
    connected, blocks the switch if any strategy has an open position (see
    Data Flow), otherwise disconnects the old feed, persists the new active
    broker, connects the new feed, and publishes `broker_active_changed`.
- Frontend (`BrokerConnections` page or equivalent) — a "Make Active" action
  per connected broker, and a visible indicator elsewhere (sidebar/dashboard)
  of which broker is currently active.
- Env vars: `UPSTOX_EXECUTION_MODE` / `UPSTOX_LIVE_TRADING_CONFIRMED` are
  renamed to broker-neutral `EXECUTION_MODE` / `LIVE_TRADING_CONFIRMED` —
  since only one broker is active at a time, one arm switch applies to
  whichever broker that is. The runtime arm switch
  (`execution/runtime_state.py`) is unchanged (already broker-neutral).

## Data flow — switching the active broker

1. `POST /api/v1/brokers/active {broker_id}` arrives.
2. Reject if `broker_id` is unknown or not connected (`is_known_broker` +
   the existing per-broker `_is_connected` check in `brokers.py`).
3. Reject if any strategy currently has an open/in-flight position
   (`ORDER_SUBMITTED` through `TARGET_2`-equivalent states across OFAO, CAS
   Dislocation, manual trading, algo trading) — an open position was opened
   using the previous broker's native instrument identifier, which a
   different broker's execution API will not recognize for the exit. The
   response reports which strategy/instrument is blocking the switch.
4. Disconnect the current active provider's feed (if any active broker,
   `await get_active_provider().disconnect_feed()`).
5. Persist the new active broker id.
6. Connect the new active provider's feed
   (`await get_active_provider().connect_feed()`).
7. Publish `broker_active_changed` on the event bus (websocket layer relays
   it to the frontend, same pattern as `ofao_state`/other broadcast events).

Every strategy engine, footprint aggregator, and manual/algo trading path
resolves the active provider/adapter *at the point of use* (not cached at
startup), so a switch takes effect on the next evaluation cycle without a
process restart.

If no broker is active (fresh install, or the active broker's credentials
are deleted): market-data-dependent strategies simply receive no ticks
(matches today's pre-login state), and `order_gateway` rejects any order
attempt with an explicit "no active broker" `REJECTED` result — it never
silently falls back to a default broker.

## Error handling / safety

- **No behavior change for existing Upstox-only usage.** With Upstox as the
  only connected+active broker, every code path behaves exactly as it does
  today. Enforced by construction: the Upstox provider/adapter wrap existing
  logic verbatim rather than reimplementing it.
- The two-factor LIVE arm switch and DRY_RUN default are untouched in
  substance (only the env var names become broker-neutral) and apply
  identically regardless of which broker is active.
- A provider/adapter failure (bad token, broker API down, transport error)
  reports the same honest `REJECTED`/`ERROR`/`OrderRejected` outcomes the
  codebase already uses — never silently substitutes a different broker or
  fabricates success.
- Phase 1 introduces no new live-money risk: Dhan/Zerodha execution does not
  exist yet in this phase, so there is nothing new to arm.

## Testing

- **Phase 1:** the full existing backend suite must stay green unchanged
  (this is the primary correctness signal for a behavior-preserving
  refactor). New tests cover: `active_broker.py` selection validation
  (unknown broker, not-connected broker, open-position block, persistence,
  event publish), and dispatch correctness (`order_gateway` calls the active
  broker's adapter; `get_active_provider()` returns the active broker's
  provider) — using a lightweight fake second provider/adapter in tests
  rather than depending on Phase 2/3 existing yet.
- **Phase 2 (Dhan) / Phase 3 (Zerodha):** unit tests against mocked
  HTTP/websocket responses, matching this session's established pattern for
  the OFAO option-chain tests. No live trading or live data verification
  without the user's own connected credentials — reported honestly as
  untested-live, same posture the codebase already takes with Upstox
  SANDBOX mode.

## Out of scope (for all three phases)

- Running multiple brokers simultaneously (explicitly ruled out — single
  active broker by design, confirmed with the user).
- Any change to the LIVE two-factor arming mechanism's *strength* — only its
  env var naming becomes broker-neutral.
- Footprint/order-flow depth data parity across brokers — today's real
  Upstox feed only provides LTP (`ltpc` mode, no market depth); the
  footprint charts' order-flow-level data is already sourced from
  `mock_feed.py`'s simulator, not real Upstox data, and that does not change
  here.
