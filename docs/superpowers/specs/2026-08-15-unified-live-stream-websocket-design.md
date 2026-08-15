# Unified `/ws/live-stream` Endpoint — Design

## Context

The original strategy-engine spec called for a single unified WebSocket
endpoint, `/ws/live-stream`, pushing one structured state object per client
containing `timestamp`, `session_phase`, `risk_status`, `active_strategy_payload`,
and `market_stats`. An audit found this doesn't exist: the actual backend
uses a generic per-channel broadcaster (`/ws/{channel}`, `backend/app/api/websockets.py`)
where every strategy/engine publishes its own raw payload to its own channel
(`market`, `oi`, `straddle`, `trending_oi`, `market_breadth`, etc.), and every
subscriber on a channel receives the identical broadcast payload.

This design adds the missing unified endpoint. It is the fourth item in a
sequence of fixes/features this session (RSI-band fix, post-3PM OI anomaly
filter, a heavyweight-banking-tracker attempt that was cancelled because the
project must not use stock futures, and now this).

## Goal

A single `GET /ws/live-stream?strategy=<id>` endpoint that pushes one
aggregated JSON payload per second to each connected client, containing:

- `timestamp` — server time at emission (ISO 8601).
- `session_phase` — one of `CONTINUOUS`, `DECAY`, `CAS`, `GOLDEN_WINDOW`,
  `CLOSED`, computed from wall-clock time.
- `risk_status` — a normalized list of pillar/filter checks for the
  client's selected strategy, each with `name`, `passed`, and
  `rejection_reason` (nullable).
- `active_strategy_payload` — the selected strategy's own current state,
  strategy-specific shape.
- `market_stats` — `{regime, oi_difference_pct, atr_progress_pct}`, sourced
  from real, already-tracked engine state.

## Explicit non-goals

- **No `heavyweight_alignment_count`.** The original spec's `market_stats`
  included this; it inherently requires per-stock futures OI, which the
  project must not use. Dropped entirely, not replaced with a substitute.
- **No universal 4-pillar risk system.** `risk_status` reflects whatever
  filter/pillar state the *selected* strategy already tracks — it is not a
  fixed set of 4 checks applied uniformly. Building genuine portfolio-level
  risk checks (daily loss limit, margin, position limits) into `risk.py`
  remains separate, larger follow-up work, not part of this endpoint.
- **Only two strategies get real `risk_status`/`active_strategy_payload`
  adapters in this pass**: `trending_oi_price_action` and `oh_ol_strategy`
  — the only two engines that currently hold real per-instrument state with
  pillar/filter-like fields. `straddle`, `two_candle`, `btst_cas`, and
  `pullback_chop` return an honest empty `risk_status: []` rather than a
  fabricated pillar structure; extending them is separate follow-up work.
- **No reuse of the existing `ConnectionManager`/`/ws/{channel}` broadcaster.**
  That manager sends one identical payload to every subscriber on a channel;
  this endpoint's payload varies per client (different clients can select
  different strategies), so it needs its own per-connection loop instead of
  the shared broadcast-to-all pattern.

## Components

### `backend/app/api/session_phase.py` (new)

```python
def compute_session_phase(now: time) -> str:
```

Pure function, no I/O. Boundaries reused from what's already hardcoded
elsewhere in the repo, for consistency with what individual strategies
already believe about the session:

- `< 09:15` → `CLOSED`
- `09:15 ≤ now < 14:30` → `CONTINUOUS` (matches `trending_oi_price_action`'s
  `trade_cutoff_time = time(14, 30)`)
- `14:30 ≤ now < 15:15` → `DECAY`
- `15:15 ≤ now < 15:35` → `CAS` (matches `BtstDashboardView.tsx`'s
  `isCasWindow` boundary)
- `15:35 ≤ now < 15:40` → `GOLDEN_WINDOW` (matches `btst_cas_engine.py`'s
  `cas_resolution_time`/`fo_close_time`)
- `≥ 15:40` → `CLOSED`

### `backend/app/api/live_stream_adapters.py` (new)

One adapter function per supported strategy, each returning
`(risk_status: list[dict], active_strategy_payload: dict)` for a given
instrument's state:

- `adapt_trending_oi_price_action(state: dict) -> tuple[list[dict], dict]`
  — reads `trending_oi_pa_engine.positions[instrument]`. Maps
  `time_filter_status`/`distance_filter_status` (already `"VALID"`/`"BLOCKED"`
  strings) into `risk_status` entries with `passed = (status == "VALID")`
  and `rejection_reason` taken from the existing `state["rejection_reason"]`
  field when blocked. `active_strategy_payload` is the position state dict
  as-is (`position_state`, `lots_held`, `avg_entry_price`, `current_sl`,
  `diff_oi_pct`, `indicator_distance`, etc.).
- `adapt_oh_ol(state) -> tuple[list[dict], dict]` — reads
  `oh_ol_strategy`'s per-instrument target state. Maps its probability
  gate and OI-shift-confirmation gate into two `risk_status` entries.
  `active_strategy_payload` is the target state as-is.

Both adapters take already-existing in-memory state — no new tracking is
added to either engine.

### `backend/app/api/endpoints/live_stream.py` (new)

```python
@router.websocket("/ws/live-stream")
async def live_stream(websocket: WebSocket, strategy: str = Query(...)):
```

- Validates `strategy` against the two supported adapters plus the
  strategies that get an honest-empty `risk_status`. Unknown values close
  the connection with code `1003` and a clear reason, matching the existing
  unknown-channel rejection pattern in `websockets.py`.
- On accept, loop every 1 second (matching `trending_oi_engine`'s existing
  1Hz publish convention) until disconnect:
  - Compute `session_phase` via `compute_session_phase(datetime.now().time())`.
  - Look up the selected strategy's current instrument state (for the
    two-supported case) or emit `risk_status: []` / `active_strategy_payload: {}`
    (for the rest). If the supported strategy has no state yet for any
    instrument (market not open, nothing has ticked), report
    `active_strategy_payload: {"status": "NO_ACTIVE_INSTRUMENT_STATE"}`
    rather than fabricating zeros for fields that don't exist yet.
  - Compute `market_stats` from already-tracked values: `diff_oi_pct` from
    the relevant engine's state, `atr_progress_pct` from
    `intraday_range / daily_atr_val * 100` (same computation
    `trending_oi_price_action` already does internally as `atr_usage`,
    just exposed) — `daily_atr_val` can be `None` before 15 daily candles
    have accumulated (`daily_atr.atr_values` empty), in which case
    `atr_progress_pct` is reported as `null`, not `0`, since `0` would
    misrepresent "not yet computable" as "no range used". `regime` from
    `gap_opening/engine.py`'s `oi_regime` dict for the instrument if
    available, else `"UNKNOWN"`.
  - `await websocket.send_json(payload)`.
- `WebSocketDisconnect` cancels the loop cleanly, same pattern as the
  existing `chart_stream`/`websocket_endpoint` handlers.

### `backend/app/main.py`

Registers the new router, same pattern as the other `app.include_router(...)`
calls already there.

## Error handling

- Unknown `strategy` query value → connection rejected at accept time with
  a clear close reason, not a silent fallback to a default strategy.
- Missing/empty `strategy` query param → FastAPI's own 422 validation
  response (required query param), consistent with how FastAPI already
  handles required params elsewhere in this codebase (e.g. `broker.py`'s
  `code: str = Query(...)`).
- Any exception while building one tick's payload is caught, logged, and
  the loop continues to the next second rather than dropping the
  connection — matches the existing `except Exception` + continue pattern
  in `market_breadth_engine.py`'s worker loop.

## Testing

- `test_session_phase.py` (new): boundary tests for
  `compute_session_phase` — one assertion per phase boundary (09:14:59 vs
  09:15:00, 14:29:59 vs 14:30:00, etc.), covering both edges of each
  window.
- `test_live_stream_adapters.py` (new): feeds synthetic
  `trending_oi_pa_engine`/`oh_ol_strategy` state into each adapter,
  asserts the mapped `risk_status`/`active_strategy_payload` shape,
  including the blocked-with-`rejection_reason` case for each.
- `test_live_stream_endpoint.py` (new): `TestClient`-based websocket test
  (matching the existing pattern in `test_websockets.py`) — connects with
  a supported strategy, receives at least one payload, asserts its top
  level shape; connects with an unsupported-but-known strategy name and
  asserts empty `risk_status`; connects with an unknown strategy name and
  asserts the connection is rejected.

No test makes a real network call or depends on live market hours — all
tests inject synthetic engine state and/or monkeypatch
`datetime.now()`/`compute_session_phase`'s input directly.
