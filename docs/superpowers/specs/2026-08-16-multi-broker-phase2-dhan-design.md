# Multi-Broker Phase 2: Dhan — Design

## Goal

Real `MarketDataProvider` + `BrokerExecutionAdapter` implementations for Dhan,
built to Dhan's documented v2 API, registered with `active_broker` alongside
Upstox. No live Dhan credentials available during development — verified
with mocked HTTP/WS responses, reported honestly as untested-live (same
posture this codebase already takes with Upstox SANDBOX mode).

## New files

- `backend/app/core/dhan_instrument_master.py` — fetches and caches Dhan's
  public instrument-master CSV (no credentials needed, it's a public file).
  Resolves `underlying -> security_id` (NIFTY/BANKNIFTY/SENSEX) and
  `(underlying, expiry, strike, option_type) -> security_id` for individual
  option contracts. A lookup miss or stale cache raises a clear error —
  never guesses an ID. Manual refresh method; no hardcoded IDs anywhere.
- `backend/app/market_data/dhan_provider.py` — `DhanProvider`, implementing
  `MarketDataProvider`:
  - `instrument_key_for_index` → resolves via the instrument master.
  - `connect_feed`/`disconnect_feed` → Dhan's binary WebSocket
    (`wss://api-feed.dhan.co`), parsing only the LTP packet type (matches
    Upstox's current real-feed fidelity — no depth, consistent with Phase
    1's documented scope).
  - `fetch_option_chain` → calls Dhan's real `/optionchain` endpoint,
    resolves each leg's `security_id` via the instrument master, and
    translates the response into the existing canonical
    `call_options`/`put_options`/`market_data`/`option_greeks` shape — zero
    strategy-code changes.
  - `fetch_quote`/`fetch_historical_candles` → Dhan's `/marketfeed/quote`
    and `/charts/historical`, translated into the existing `Quote` /
    canonical candle-row shapes.
- `backend/app/execution/dhan_adapter.py` — `DhanExecutionAdapter`,
  implementing `BrokerExecutionAdapter`. `place_order` maps `OrderRequest`
  to Dhan's `/orders` POST body:
  - `product`: `"I"→INTRADAY`, `"D"→CNC`, `"MTF"→MTF`
  - `order_type`: `"MARKET"→MARKET`, `"LIMIT"→LIMIT`, `"SL"→STOP_LOSS`,
    `"SL-M"→STOP_LOSS_MARKET`
  - `SANDBOX` mode returns `REJECTED` with "Dhan has no sandbox
    environment" — never silently routes to LIVE. `DRY_RUN` and `LIVE`
    behave normally. Only reports `SUBMITTED` when Dhan returns a real
    `orderId`.

## Registration

`main.py` registers `dhan_provider`/`dhan_execution_adapter`/`dhan_auth`
with `active_broker` at import time, same pattern as Upstox — no auto-
activation (only Upstox auto-activates today, per Phase 1; Dhan only
becomes active via an explicit `POST /api/v1/brokers/active`).

## Testing

Unit tests against mocked HTTP responses (option chain, order placement,
quote, historical candles) and synthetic binary packets built from Dhan's
documented packet format for the LTP feed parser. No live Dhan account
exists to verify against — the binary packet parser specifically carries
real risk of a subtle framing/offset bug that only a live connection would
surface; this is a named, accepted limitation, not glossed over.

## Out of scope for Phase 2

Full market depth parsing; running Dhan simultaneously with another broker
(ruled out platform-wide in Phase 1); any Zerodha work (Phase 3).
