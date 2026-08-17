# Frontend Live-Data Wiring — Phase 1 — Design

## Context

A survey of every page in `frontend/src/App.tsx` found most pages fall into
two buckets: already wired to real backend data (confirmed directly, not
assumed — CAS Dislocation, OFAO, Execution Control, Algo Dashboard, Broker
Connections/Upstox, Order Flow, Backtest all make real `fetch`/WebSocket
calls today), or genuinely unwired with no backend feature to wire to
(~25 pages — Option Chain, Greeks, Decision Intel, Risk, PnL, most
standalone strategy dashboards, etc.), which become Phases 2-5.

This spec covers the actual remaining gap in the "wire what already has a
backend" bucket: three pages, none of which turned out to be pure wiring
on inspection.

- **Positions** (`PositionPanel`) — genuinely pure wiring. Reads a
  mock-seeded store; real data exists at `GET /api/v1/manual-trading/positions`
  and `GET /api/v1/cas-dislocation/positions`.
- **Orders** (`OrderPanel`) — needs a small new backend piece. No order-history
  endpoint exists; the `executions` DuckDB table (in
  `backend/app/workers/persistence.py`) is already defined but nothing
  publishes to it.
- **Levels** (`LevelPanel`) — needs a small new backend piece. The
  `/api/v1/levels/{instrument}` endpoint exists and is registered, but no
  `LevelEngine` was ever implemented — `set_level_engine()` is never called,
  so it always returns `[]`.

## Positions

`GET /api/v1/manual-trading/positions` returns `ManualPosition[]`,
`GET /api/v1/cas-dislocation/positions` returns `CASPosition[]` — both
Pydantic models with: `position_id, underlying, option_type, strike,
instrument_token, quantity, entry_price, status, created_at, closed_at,
exit_reason` (plus a few strategy-specific fields). Neither carries option
greeks, LTP, or a computed P&L — those exist in the frontend's mock
`Position` interface but have no real source today.

Rather than fabricate greeks/P&L to match the existing mock shape, the
frontend `Position` interface changes to only the fields real data has:
`id, instrument, strike, optionType, quantity, entryPrice, status,
source ("MANUAL" | "CAS"), createdAt, closedAt`. `PositionPanel` fetches
both endpoints, tags each row with its source, merges, and renders. Only
`status === "OPEN"` rows are "active" for any active-position counts
elsewhere. No polling interval is invented — a page-mount fetch plus a
manual refresh button is enough for Phase 1 (neither endpoint pushes
updates over a websocket today; adding that is out of scope here).

## Orders (execution log)

**Backend:** `engines/execution.py` is the one place in the codebase that
calls `order_gateway.place_order()` and gets an `OrderResult` back — it
already knows `status` and can derive `instrument`/`action` from the
`DECISION_CREATED` payload it consumed. Add one line there:
`await event_bus.publish("persist_execution", {...})` with the fields the
existing `executions` table already declares (`instrument, action,
status`, `timestamp` defaults itself) — the persistence worker already
subscribes to this channel and inserts (`persistence.py:19`), it has just
never received anything. No schema change.

Add `GET /api/v1/executions` (new endpoint, new tiny router or added to
an existing one — implementer's choice, follow the codebase's existing
router-per-feature pattern) reading the `executions` table via the
persistence worker's DuckDB connection, most-recent-first, capped at a
reasonable limit (e.g. 200) since this is a raw log, not paginated in
Phase 1.

**Frontend:** the `Order` interface drops fields with no real source
(`brokerOrderId, decision, risk, executionDetails` — none of these exist
in the `executions` table) down to: `timestamp, instrument, action,
status`. `OrderPanel` fetches `GET /api/v1/executions` on mount plus a
manual refresh button, same pattern as Positions.

## Levels (pivot-point engine)

**Backend:** new `backend/app/engines/level_engine.py` (or under
`strategies/`, matching wherever similar lightweight engines live — check
`backend/app/engines/` for the existing pattern before picking a
location). Computes standard CPR/pivot levels from the **previous
trading day's** daily candle: `fetch_historical_candles` via
`active_broker.get_active_provider()` for a small `from_date`/`to_date`
window ending yesterday, taking the most recent completed daily candle's
high/low/close.

Standard formulas (previous day's H/L/C):
- Pivot `P = (H + L + C) / 3`
- `R1 = 2P - L`, `S1 = 2P - H`
- `R2 = P + (H - L)`, `S2 = P - (H - L)`
- CPR: `TC = (P - BC) + P` where `BC = (H + L) / 2`, `Pivot = P`

Output shape matches what `levels.py`'s existing `l.model_dump()` /
`l.level_type` calls already expect (`Level` model with `level_type` one
of `"Support"`/`"Resistance"`/`"Pivot"`/`"CPR"` — check the exact existing
`Level` Pydantic model, if one already exists partially defined, and match
it rather than inventing a parallel shape). Compute for NIFTY and SENSEX
(the two instruments Levels pages exist for today). `set_level_engine()`
gets called once at app startup in `main.py`, same pattern as every other
engine.

If `active_broker` has no active provider (no broker connected/active) or
the historical-candle fetch fails, `active_levels` for that instrument
stays empty — matches the existing honest-empty behavior, no fabricated
levels.

**Frontend:** `LevelPanel` drops its hardcoded `priceData`/CPR literals,
fetches `GET /api/v1/levels/{instrument}` on mount, renders whatever
comes back (including genuinely empty, if no broker is active — the UI
should say so, not show stale/fake numbers).

## Testing

Backend: unit tests for the pivot-point formulas against known
input/output pairs (no live broker needed — mock the historical-candle
fetch); a test that `persist_execution` fires with the right payload shape
after a `place_order` call; a test that `GET /api/v1/executions` returns
what was inserted. Frontend: existing test patterns in this codebase are
sparse for panel components — match whatever precedent exists (check for
`.test.tsx` siblings of `PositionPanel`/`OrderPanel`/`LevelPanel` before
deciding whether to add one from scratch).

## Out of scope

Websocket/push updates for Positions or Orders (poll-on-demand only, this
phase); pagination for the execution log; option greeks or live P&L on
positions (no real source yet — would need live quotes per position,
which is Phase 3 territory); Fibonacci retracement levels on the Levels
page (CPR + standard pivots only, matching what's realistically computable
from daily candles alone).
