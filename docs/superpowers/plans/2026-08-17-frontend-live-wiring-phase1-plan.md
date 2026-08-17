# Frontend Live-Data Wiring Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Positions, Orders, and Levels off mock data onto real backend data — Positions/Orders via existing endpoints, Levels by wiring an existing-but-never-started real-time support/resistance engine.

**Architecture:** Backend: (1) publish real execution results to the already-defined-but-unused `executions` DuckDB table, and add a `GET /api/v1/executions` reader; (2) wire `TickProcessor`'s candle aggregators + `LevelEngine` into the real `MARKET_TICK` stream at startup (data-only — the separate `LevelStrategyEngine` trading strategies are explicitly not wired). Frontend: three components (`PositionPanel`, `OrderPanel`, `LevelPanel`) get their own fetch logic and real-data-shaped types, decoupled from the existing `usePortfolioStore` mock store (which stays untouched — other still-mockup pages depend on it).

**Tech Stack:** FastAPI, DuckDB (via the existing `AsyncPersistenceWorker`), pytest + pytest-asyncio, React/TypeScript, Vitest.

## Global Constraints

- Never fabricate data. If a real source is empty (no broker active, no executions yet, no levels detected yet), the UI shows an honest empty state — never a stale/mock number.
- `LevelStrategyEngine` (the 8 level-based trading strategies) is explicitly NOT wired in this plan — only `LevelEngine` (detection/data, no trading signals). This keeps the blast radius to a read-only dashboard feature.
- `TickProcessor.process()` must never be the `MARKET_TICK` subscriber callback — it re-publishes `MARKET_TICK` itself, which would create an infinite loop if triggered by a `MARKET_TICK` event. Feed candle aggregators directly via their own `process_tick()`.
- `usePortfolioStore` (the existing mock store, its test file, and `useLiveFeedSimulator`) stay untouched — Dashboard/PnL pages still depend on them and are out of scope for this phase.
- Full existing backend test suite must stay green: this plan does not touch anything that should change the current pass/fail counts except by potentially fixing `test_integration.py::test_full_event_flow` as a side effect of wiring `LevelEngine`/`TickProcessor` into `main.py` — that test constructs its own isolated pipeline and does not depend on `main.py`, so it is not expected to change, but is worth checking after Task 1.

---

## File Structure

New files:
- `backend/app/api/endpoints/executions.py` — `GET /api/v1/executions`.
- `backend/tests/test_executions_api.py`, `backend/tests/test_execution_persist_publish.py`, `backend/tests/test_main_level_engine_startup.py`.
- `frontend/src/hooks/useLivePositions.ts`, `frontend/src/hooks/useLiveOrders.ts`, `frontend/src/hooks/useLiveLevels.ts` — small fetch-on-mount hooks, one per feature, matching this codebase's existing "one hook per data source" pattern.
- `frontend/src/types/live.ts` — the new, real-data-shaped TypeScript interfaces (`LivePosition`, `LiveOrder`, `LiveLevel`), kept separate from `mock/interfaces.ts` since they describe different data.

Modified files:
- `backend/app/engines/execution.py` — publish `persist_execution` after every order result.
- `backend/app/main.py` — register `executions_router`; wire `TickProcessor` + `LevelEngine` into the real `MARKET_TICK` stream at startup.
- `frontend/src/components/PositionPanel.tsx`, `frontend/src/components/OrderPanel.tsx`, `frontend/src/components/LevelPanel.tsx` — switch from `usePortfolioStore`/hardcoded literals to the new hooks/types.
- `frontend/src/App.tsx` — thread an `instrument` prop into `<LevelPanel />` for `MARKET_NIFTY`/`MARKET_SENSEX`.

---

### Task 1: Publish real execution results to the `executions` table

**Files:**
- Modify: `backend/app/engines/execution.py`
- Test: `backend/tests/test_execution_persist_publish.py`

**Interfaces:**
- Consumes: the existing `executions` DuckDB table schema (`timestamp` default, `instrument VARCHAR`, `action VARCHAR`, `status VARCHAR`) already declared in `backend/app/workers/persistence.py`, and the existing `event_bus.subscribe("persist_execution", self._enqueue_event)` subscription in that same file (already wired, never fed).
- Produces: `ExecutionEngine.execute_order()` now also publishes `"persist_execution"` with `{"instrument": str, "action": str, "status": str}` — `action` is `"{transaction_type} {instrument}"` (e.g. `"BUY NIFTY 25000 CE"`) to keep the single `action` column self-describing without a schema change.

This is a two-line addition to an already-tested method — the existing `_publish_update` call and its inputs are unchanged.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_execution_persist_publish.py
from unittest.mock import AsyncMock

import pytest

from backend.app.engines import execution as execution_module
from backend.app.engines.execution import ExecutionEngine
from backend.app.execution.order_gateway import ExecutionMode, OrderResult


@pytest.mark.asyncio
async def test_execute_order_publishes_persist_execution(monkeypatch):
    published = []

    async def fake_publish(channel, payload):
        published.append((channel, payload))

    monkeypatch.setattr(execution_module.event_bus, "publish", fake_publish)
    monkeypatch.setattr(
        execution_module.order_gateway, "place_order",
        AsyncMock(return_value=OrderResult(status="DRY_RUN", mode=ExecutionMode.DRY_RUN, payload={}, detail="ok")),
    )

    engine = ExecutionEngine()
    await engine.execute_order({
        "instrument": "NIFTY 25000 CE", "instrument_token": "NSE_FO|123",
        "transaction_type": "BUY", "quantity": 75, "price": 100.0,
        "decision_id": "dec_1", "source": "MANUAL",
    })

    persist_events = [p for ch, p in published if ch == "persist_execution"]
    assert len(persist_events) == 1
    assert persist_events[0]["instrument"] == "NIFTY 25000 CE"
    assert persist_events[0]["action"] == "BUY NIFTY 25000 CE"
    assert persist_events[0]["status"] == "DRY_RUN"


@pytest.mark.asyncio
async def test_execute_order_publishes_persist_execution_even_on_rejection(monkeypatch):
    published = []

    async def fake_publish(channel, payload):
        published.append((channel, payload))

    monkeypatch.setattr(execution_module.event_bus, "publish", fake_publish)

    engine = ExecutionEngine()
    await engine.execute_order({
        "instrument": "NIFTY 25000 CE", "instrument_token": None,
        "transaction_type": "BUY", "quantity": 75, "price": 100.0,
        "decision_id": "dec_1", "source": "MANUAL",
    })

    persist_events = [p for ch, p in published if ch == "persist_execution"]
    assert len(persist_events) == 1
    assert persist_events[0]["status"] == "REJECTED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_execution_persist_publish.py -v`
Expected: FAIL — only 0 or 1 `persist_execution` events depending on path, since neither branch publishes it yet (both currently only publish `EXECUTION_UPDATE`)

- [ ] **Step 3: Add the publish call**

In `backend/app/engines/execution.py`, both call sites of `await self._publish_update(...)` (the early `REJECTED` return for no `instrument_token`, and the normal path after `order_gateway.place_order`) need a follow-up publish. Add this right after each `await self._publish_update(...)` call:

```python
        await event_bus.publish("persist_execution", {
            "instrument": instrument,
            "action": f"{req_data.get('transaction_type', 'BUY')} {instrument}",
            "status": "REJECTED" if not instrument_token else result.status,
        })
```

For the early-return (no `instrument_token`) branch, `result` doesn't exist yet — use this instead, right after that branch's `_publish_update` call:

```python
        await event_bus.publish("persist_execution", {
            "instrument": instrument,
            "action": f"{req_data.get('transaction_type', 'BUY')} {instrument}",
            "status": "REJECTED",
        })
        return
```

(the existing early-return already has `return` after `_publish_update` — add the new publish before that `return`, not after).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_execution_persist_publish.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/engines/execution.py backend/tests/test_execution_persist_publish.py
git commit -m "feat: publish persist_execution so the executions table actually gets rows"
```

---

### Task 2: `GET /api/v1/executions`

**Files:**
- Create: `backend/app/api/endpoints/executions.py`
- Modify: `backend/app/main.py` (register the router)
- Test: `backend/tests/test_executions_api.py`

**Interfaces:**
- Consumes: `persistence_worker` singleton from `backend/app/workers/persistence.py` (`persistence_worker.conn` — a DuckDB connection; use `.cursor()` for the read query to avoid any concurrency conflict with the worker's own writes on its executor thread).
- Produces: `GET /api/v1/executions?limit=200` → `List[{"timestamp": str, "instrument": str, "action": str, "status": str}]`, most-recent-first.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_executions_api.py
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.workers.persistence import persistence_worker


@pytest.fixture
def client():
    return TestClient(app)


def _insert_execution(instrument: str, action: str, status: str):
    persistence_worker.conn.execute(
        "INSERT INTO executions (instrument, action, status) VALUES (?, ?, ?)",
        [instrument, action, status],
    )


def test_get_executions_returns_most_recent_first(client):
    _insert_execution("NIFTY 25000 CE", "BUY NIFTY 25000 CE", "DRY_RUN")
    _insert_execution("SENSEX 80000 PE", "SELL SENSEX 80000 PE", "SUBMITTED")

    res = client.get("/api/v1/executions")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) >= 2
    # most recent insert (SENSEX) appears before the earlier one (NIFTY)
    sensex_idx = next(i for i, r in enumerate(rows) if r["instrument"] == "SENSEX 80000 PE")
    nifty_idx = next(i for i, r in enumerate(rows) if r["instrument"] == "NIFTY 25000 CE")
    assert sensex_idx < nifty_idx
    assert rows[sensex_idx]["status"] == "SUBMITTED"


def test_get_executions_respects_limit(client):
    for i in range(5):
        _insert_execution(f"TEST{i}", f"BUY TEST{i}", "DRY_RUN")

    res = client.get("/api/v1/executions?limit=3")
    assert res.status_code == 200
    assert len(res.json()) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_executions_api.py -v`
Expected: FAIL with 404 (route doesn't exist)

- [ ] **Step 3: Implement**

```python
# backend/app/api/endpoints/executions.py
"""Read-only view of the executions log — real order-result rows
published by ExecutionEngine (see engines/execution.py's
persist_execution publish) and persisted by AsyncPersistenceWorker.
"""

from fastapi import APIRouter

from backend.app.workers.persistence import persistence_worker

router = APIRouter(prefix="/api/v1/executions", tags=["executions"])


@router.get("")
async def list_executions(limit: int = 200):
    cursor = persistence_worker.conn.cursor()
    rows = cursor.execute(
        "SELECT timestamp, instrument, action, status FROM executions "
        "ORDER BY timestamp DESC LIMIT ?",
        [limit],
    ).fetchall()
    return [
        {"timestamp": str(r[0]), "instrument": r[1], "action": r[2], "status": r[3]}
        for r in rows
    ]
```

In `backend/app/main.py`, add the import near the other endpoint imports (e.g. next to `from backend.app.api.endpoints.backtest import router as backtest_router`):

```python
from backend.app.api.endpoints.executions import router as executions_router
```

And register it alongside the other `app.include_router(...)` calls:

```python
app.include_router(executions_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_executions_api.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/endpoints/executions.py backend/app/main.py backend/tests/test_executions_api.py
git commit -m "feat: add GET /api/v1/executions reading the real execution log"
```

---

### Task 3: Wire `TickProcessor` + `LevelEngine` into the real `MARKET_TICK` stream

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_main_level_engine_startup.py`

**Interfaces:**
- Consumes: `TickProcessor`, `CandleAggregator` (`backend/app/market_data/processor.py`, unchanged); `LevelEngine` (`backend/app/levels/engine.py`, unchanged — `.start()` already subscribes itself to `CANDLE_CLOSED`); `set_level_engine` (`backend/app/api/endpoints/levels.py`, unchanged).
- Produces: at app startup, `main.py` holds a `TickProcessor` and `LevelEngine` instance, a `MARKET_TICK` subscriber that feeds the aggregators directly (not via `TickProcessor.process()`), and `set_level_engine(level_engine)` has been called so `GET /api/v1/levels/{instrument}` returns real data once ticks/candles/levels exist.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_main_level_engine_startup.py
import pytest


@pytest.mark.asyncio
async def test_level_engine_registered_and_subscribed_to_market_tick():
    import backend.app.main as main_module
    from backend.app.api.endpoints.levels import get_level_engine
    from backend.app.core.event_bus import event_bus
    from backend.app.market_data.models import Tick
    from datetime import datetime, timezone

    # main.py registers set_level_engine(...) at import time is NOT the
    # pattern used elsewhere in this codebase (active_broker registration
    # is import-time, but engine construction/wiring happens inside
    # lifespan) — so this test drives the lifespan startup directly.
    async with main_module.app.router.lifespan_context(main_module.app):
        engine = get_level_engine()
        assert engine is not None

        published = []

        async def capture(data):
            published.append(data)

        event_bus.subscribe("CANDLE_CLOSED", capture)

        # Feed enough ticks across 3m candle boundaries to force at least
        # one candle close on the fastest (3-minute) aggregator.
        base = datetime(2024, 1, 1, 9, 15, 0, tzinfo=timezone.utc)
        await event_bus.publish("MARKET_TICK", Tick(instrument="NIFTY", price=100.0, volume=10, timestamp=base))
        await event_bus.publish("MARKET_TICK", Tick(instrument="NIFTY", price=105.0, volume=10, timestamp=base.replace(minute=18)))

        import asyncio
        await asyncio.sleep(0.05)

        assert len(published) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_main_level_engine_startup.py -v`
Expected: FAIL — `get_level_engine()` returns `None` (nothing calls `set_level_engine` yet)

- [ ] **Step 3: Wire it in `main.py`**

Add imports near the other engine imports:

```python
from backend.app.market_data.processor import TickProcessor
from backend.app.levels.engine import LevelEngine
from backend.app.api.endpoints.levels import set_level_engine
```

Inside the `lifespan` function, in the startup section (alongside the other `*.start()` calls, e.g. right after `market_breadth_engine.start()`), add:

```python
    tick_processor = TickProcessor()
    level_engine = LevelEngine()
    set_level_engine(level_engine)
    level_engine.start()

    async def _feed_candle_aggregators(tick) -> None:
        # NOT tick_processor.process(tick) — that method itself publishes
        # MARKET_TICK, and this callback IS the MARKET_TICK subscriber;
        # calling it here would re-publish and re-trigger itself forever.
        for aggregator in tick_processor.aggregators:
            await aggregator.process_tick(tick)

    event_bus.subscribe("MARKET_TICK", _feed_candle_aggregators)
```

This does not need a corresponding shutdown/stop call — `LevelEngine`/`CandleAggregator` hold only in-memory state and unsubscribing individual event-bus callbacks isn't a pattern this codebase uses elsewhere (the other engines' `.stop()` methods just flip a `_started`/`running` flag; `LevelEngine`/`TickProcessor` have no such flag to flip, and leaving the subscription active until process exit matches how every other `event_bus.subscribe` in `main.py`'s startup section already behaves).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_main_level_engine_startup.py -v`
Expected: 1 passed

- [ ] **Step 5: Run the full suite, then commit**

Run: `cd backend && python -m pytest -q`
Expected: no new failures beyond the existing 3 pre-existing unrelated ones (`test_bullish_setup`, `test_full_event_flow`, `test_candle_aggregation_no_look_ahead`) — note `test_full_event_flow` builds its own isolated pipeline unconnected to `main.py`, so it is not expected to flip to passing here; if it does, that's a bonus, not a requirement.

```bash
git add backend/app/main.py backend/tests/test_main_level_engine_startup.py
git commit -m "feat: wire TickProcessor + LevelEngine into the real MARKET_TICK stream at startup"
```

---

### Task 4: Frontend — real `PositionPanel`

**Files:**
- Create: `frontend/src/types/live.ts` (start this task's edits here; Tasks 5/6 add to the same file)
- Create: `frontend/src/hooks/useLivePositions.ts`
- Modify: `frontend/src/components/PositionPanel.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/manual-trading/positions` (existing, returns `ManualPosition[]` — fields `position_id, underlying, option_type, strike, instrument_token, expiry_date, lots, quantity, entry_price, stop_loss, target, status, created_at, closed_at, exit_reason`); `GET /api/v1/cas-dislocation/positions` (existing, returns `CASPosition[]` — fields `position_id, underlying, option_type, strike, instrument_token, lots, quantity, entry_price, status, created_at, opened_at, closed_at, exit_reason, last_ltp`).
- Produces: `LivePosition` type in `frontend/src/types/live.ts`; `useLivePositions()` hook returning `{positions: LivePosition[], loading: boolean, error: string | null, refetch: () => void}`.

- [ ] **Step 1: Add the `LivePosition` type**

```typescript
// frontend/src/types/live.ts
export interface LivePosition {
  id: string;
  source: 'MANUAL' | 'CAS';
  instrument: string; // e.g. "NIFTY 25000 CE"
  strike: number;
  optionType: 'CE' | 'PE';
  quantity: number;
  entryPrice: number;
  status: 'PENDING' | 'OPEN' | 'CLOSED';
  createdAt: string;
  closedAt: string | null;
  exitReason: string | null;
}
```

- [ ] **Step 2: Write the hook**

```typescript
// frontend/src/hooks/useLivePositions.ts
import { useCallback, useEffect, useState } from 'react';
import type { LivePosition } from '../types/live';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface RawManualPosition {
  position_id: string; underlying: string; option_type: 'CE' | 'PE'; strike: number;
  quantity: number; entry_price: number; status: 'PENDING' | 'OPEN' | 'CLOSED';
  created_at: string; closed_at: string | null; exit_reason: string | null;
}

interface RawCASPosition extends RawManualPosition {}

function toLivePosition(raw: RawManualPosition, source: 'MANUAL' | 'CAS'): LivePosition {
  return {
    id: `${source}_${raw.position_id}`,
    source,
    instrument: `${raw.underlying} ${raw.strike} ${raw.option_type}`,
    strike: raw.strike,
    optionType: raw.option_type,
    quantity: raw.quantity,
    entryPrice: raw.entry_price,
    status: raw.status,
    createdAt: raw.created_at,
    closedAt: raw.closed_at,
    exitReason: raw.exit_reason,
  };
}

export function useLivePositions() {
  const [positions, setPositions] = useState<LivePosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [manualRes, casRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/manual-trading/positions`),
        fetch(`${API_BASE}/api/v1/cas-dislocation/positions`),
      ]);
      if (!manualRes.ok) throw new Error(`manual-trading/positions failed (${manualRes.status})`);
      if (!casRes.ok) throw new Error(`cas-dislocation/positions failed (${casRes.status})`);
      const manual: RawManualPosition[] = await manualRes.json();
      const cas: RawCASPosition[] = await casRes.json();
      setPositions([
        ...manual.map((p) => toLivePosition(p, 'MANUAL')),
        ...cas.map((p) => toLivePosition(p, 'CAS')),
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load positions');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { positions, loading, error, refetch };
}
```

- [ ] **Step 3: Rewrite `PositionPanel.tsx`**

```tsx
// frontend/src/components/PositionPanel.tsx
import React from 'react';
import { useLivePositions } from '../hooks/useLivePositions';
import FoldableDataTable from './FoldableDataTable';
import type { Column } from './FoldableDataTable';
import StatusBadge from './StatusBadge';
import type { LivePosition } from '../types/live';

export const PositionPanel: React.FC = () => {
  const { positions, loading, error, refetch } = useLivePositions();

  const columns: Column<LivePosition>[] = [
    {
      header: 'Instrument',
      accessor: (item) => <span className="font-bold text-zinc-100">{item.instrument}</span>,
    },
    {
      header: 'Source',
      accessor: (item) => <StatusBadge status={item.source} />,
      align: 'center',
    },
    {
      header: 'Qty',
      accessor: (item) => <span className="font-mono text-zinc-300 tabular-nums">{item.quantity}</span>,
      align: 'right',
    },
    {
      header: 'Entry Price',
      accessor: (item) => <span className="font-mono text-zinc-200 tabular-nums">₹{item.entryPrice.toFixed(2)}</span>,
      align: 'right',
    },
    {
      header: 'Status',
      accessor: (item) => <StatusBadge status={item.status} />,
      align: 'center',
    },
  ];

  const renderExpanded = (item: LivePosition) => (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 select-none p-2 text-xs">
      <div>
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Created</p>
        <p className="font-mono text-sm text-zinc-200 mt-1">{item.createdAt}</p>
      </div>
      <div>
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Closed</p>
        <p className="font-mono text-sm text-zinc-200 mt-1">{item.closedAt ?? '—'}</p>
      </div>
      <div>
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Exit Reason</p>
        <p className="text-zinc-300 mt-1">{item.exitReason ?? '—'}</p>
      </div>
      <div>
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">Option Type</p>
        <p className="text-zinc-300 mt-1">{item.optionType}</p>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
            Open Positions Monitor
          </h3>
          <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Real positions from Manual Trading and CAS Dislocation</p>
        </div>
        <button
          onClick={refetch}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg text-xs font-sans bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 disabled:opacity-40"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-mono px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {!error && positions.length === 0 && !loading && (
        <div className="text-xs text-zinc-500 font-mono px-4 py-6 text-center border border-zinc-800 rounded-lg">
          No positions.
        </div>
      )}

      {positions.length > 0 && (
        <FoldableDataTable
          data={positions}
          columns={columns}
          rowKey={(item) => item.id}
          renderExpanded={renderExpanded}
        />
      )}
    </div>
  );
};

export default PositionPanel;
```

- [ ] **Step 4: Manual verification**

Start backend + frontend, navigate to the Positions page, confirm it fetches both endpoints (check network tab) and renders an empty state (no positions exist yet in a fresh environment) rather than erroring or showing stale mock rows.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/live.ts frontend/src/hooks/useLivePositions.ts frontend/src/components/PositionPanel.tsx
git commit -m "feat: wire PositionPanel to real manual-trading + cas-dislocation positions"
```

---

### Task 5: Frontend — real `OrderPanel`

**Files:**
- Modify: `frontend/src/types/live.ts` (add `LiveOrder`)
- Create: `frontend/src/hooks/useLiveOrders.ts`
- Modify: `frontend/src/components/OrderPanel.tsx`

**Interfaces:**
- Consumes: `GET /api/v1/executions` (Task 2) → `List[{"timestamp": str, "instrument": str, "action": str, "status": str}]`.
- Produces: `LiveOrder` type; `useLiveOrders()` hook, same shape as `useLivePositions()`.

- [ ] **Step 1: Add `LiveOrder` to `frontend/src/types/live.ts`**

```typescript
export interface LiveOrder {
  id: string;
  timestamp: string;
  instrument: string;
  action: string;
  status: string;
}
```

- [ ] **Step 2: Write the hook**

```typescript
// frontend/src/hooks/useLiveOrders.ts
import { useCallback, useEffect, useState } from 'react';
import type { LiveOrder } from '../types/live';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface RawExecution {
  timestamp: string; instrument: string; action: string; status: string;
}

export function useLiveOrders() {
  const [orders, setOrders] = useState<LiveOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/executions`);
      if (!res.ok) throw new Error(`executions fetch failed (${res.status})`);
      const raw: RawExecution[] = await res.json();
      setOrders(raw.map((r, i) => ({
        id: `${r.timestamp}_${i}`,
        timestamp: r.timestamp,
        instrument: r.instrument,
        action: r.action,
        status: r.status,
      })));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load executions');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { orders, loading, error, refetch };
}
```

- [ ] **Step 3: Rewrite `OrderPanel.tsx`**

```tsx
// frontend/src/components/OrderPanel.tsx
import React from 'react';
import { useLiveOrders } from '../hooks/useLiveOrders';
import FoldableDataTable from './FoldableDataTable';
import type { Column } from './FoldableDataTable';
import StatusBadge from './StatusBadge';
import type { LiveOrder } from '../types/live';

export const OrderPanel: React.FC = () => {
  const { orders, loading, error, refetch } = useLiveOrders();

  const columns: Column<LiveOrder>[] = [
    {
      header: 'Time',
      accessor: (item) => <span className="font-mono text-zinc-400">{item.timestamp}</span>,
    },
    {
      header: 'Instrument',
      accessor: (item) => <span className="font-bold text-zinc-100">{item.instrument}</span>,
    },
    {
      header: 'Action',
      accessor: (item) => <span className="font-mono text-zinc-300">{item.action}</span>,
    },
    {
      header: 'Status',
      accessor: (item) => <StatusBadge status={item.status} />,
      align: 'center',
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
            Orders Execution Log
          </h3>
          <p className="text-xs text-zinc-400 font-sans mt-0.5 font-medium">Real execution results, most recent first</p>
        </div>
        <button
          onClick={refetch}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg text-xs font-sans bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 disabled:opacity-40"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-mono px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {!error && orders.length === 0 && !loading && (
        <div className="text-xs text-zinc-500 font-mono px-4 py-6 text-center border border-zinc-800 rounded-lg">
          No executions logged yet.
        </div>
      )}

      {orders.length > 0 && (
        <FoldableDataTable
          data={orders}
          columns={columns}
          rowKey={(item) => item.id}
        />
      )}
    </div>
  );
};

export default OrderPanel;
```

- [ ] **Step 4: Manual verification**

Confirm the Orders page fetches `/api/v1/executions` and shows the honest empty state on a fresh environment.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/live.ts frontend/src/hooks/useLiveOrders.ts frontend/src/components/OrderPanel.tsx
git commit -m "feat: wire OrderPanel to the real execution log"
```

---

### Task 6: Frontend — real `LevelPanel`

**Files:**
- Modify: `frontend/src/types/live.ts` (add `LiveLevel`)
- Create: `frontend/src/hooks/useLiveLevels.ts`
- Modify: `frontend/src/components/LevelPanel.tsx`
- Modify: `frontend/src/App.tsx` (thread `instrument` prop)

**Interfaces:**
- Consumes: `GET /api/v1/levels/{instrument}` (existing route, now real data per Task 3) → `List[Level]` where `Level` has `level_id, instrument, price, zone_low, zone_high, level_type ("Support"|"Resistance"), timeframe, strength, confidence, touch_count, source, active`.
- Produces: `LiveLevel` type; `useLiveLevels(instrument: string)` hook.
- The instrument key used for `MARKET_NIFTY`/`MARKET_SENSEX` must match what the real `Tick.instrument` field actually carries for those underlyings — check `backend/app/market_data/symbols.py`'s `INDEX_INSTRUMENT_KEYS` (e.g. `"NSE_INDEX|Nifty 50"`) since that's the string the real feed publishes and `CandleAggregator`/`LevelEngine` key their state by, not the bare `"NIFTY"` string used elsewhere in this codebase's UI layer.

- [ ] **Step 1: Add `LiveLevel` to `frontend/src/types/live.ts`**

```typescript
export interface LiveLevel {
  levelId: string;
  price: number;
  levelType: 'Support' | 'Resistance';
  timeframe: string;
  strength: number;
  touchCount: number;
}
```

- [ ] **Step 2: Write the hook**

```typescript
// frontend/src/hooks/useLiveLevels.ts
import { useCallback, useEffect, useState } from 'react';
import type { LiveLevel } from '../types/live';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface RawLevel {
  level_id: string; price: number; level_type: 'Support' | 'Resistance';
  timeframe: string; strength: number; touch_count: number;
}

export function useLiveLevels(instrument: string) {
  const [levels, setLevels] = useState<LiveLevel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/levels/${encodeURIComponent(instrument)}`);
      if (!res.ok) throw new Error(`levels fetch failed (${res.status})`);
      const raw: RawLevel[] = await res.json();
      setLevels(raw.map((r) => ({
        levelId: r.level_id,
        price: r.price,
        levelType: r.level_type,
        timeframe: r.timeframe,
        strength: r.strength,
        touchCount: r.touch_count,
      })));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load levels');
    } finally {
      setLoading(false);
    }
  }, [instrument]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { levels, loading, error, refetch };
}
```

- [ ] **Step 3: Rewrite `LevelPanel.tsx`**

```tsx
// frontend/src/components/LevelPanel.tsx
import React from 'react';
import { useLiveLevels } from '../hooks/useLiveLevels';

interface LevelPanelProps {
  instrument: string;
}

export const LevelPanel: React.FC<LevelPanelProps> = ({ instrument }) => {
  const { levels, loading, error, refetch } = useLiveLevels(instrument);

  const resistance = levels.filter((l) => l.levelType === 'Resistance').sort((a, b) => a.price - b.price);
  const support = levels.filter((l) => l.levelType === 'Support').sort((a, b) => b.price - a.price);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-zinc-100 font-sans font-bold text-base tracking-wider uppercase">
            Market Levels
          </h3>
          <p className="text-xs text-zinc-400 font-sans mt-0.5">Real-time swing-based support/resistance from live candles</p>
        </div>
        <button
          onClick={refetch}
          disabled={loading}
          className="px-3 py-1.5 rounded-lg text-xs font-sans bg-zinc-900 border border-zinc-800 text-zinc-400 hover:text-zinc-200 disabled:opacity-40"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-mono px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {!error && levels.length === 0 && !loading && (
        <div className="text-xs text-zinc-500 font-mono px-4 py-6 text-center border border-zinc-800 rounded-lg">
          No levels detected yet — needs enough closed candles from a live feed.
        </div>
      )}

      {levels.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-4">
          <div>
            <h4 className="text-rose-400 font-sans text-xs font-bold uppercase tracking-wider mb-2">Resistance</h4>
            <div className="space-y-2 font-mono text-sm">
              {resistance.map((l) => (
                <div key={l.levelId} className="flex justify-between border-b border-zinc-800/60 pb-2">
                  <span className="text-zinc-400">{l.timeframe} · touched {l.touchCount}x</span>
                  <span className="text-zinc-100 font-semibold">{l.price.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <h4 className="text-emerald-400 font-sans text-xs font-bold uppercase tracking-wider mb-2">Support</h4>
            <div className="space-y-2 font-mono text-sm">
              {support.map((l) => (
                <div key={l.levelId} className="flex justify-between border-b border-zinc-800/60 pb-2">
                  <span className="text-zinc-400">{l.timeframe} · touched {l.touchCount}x</span>
                  <span className="text-zinc-100 font-semibold">{l.price.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LevelPanel;
```

Note: this drops the `ChartPanel` price-chart rendering that used hardcoded `priceData` — there is no real intraday price-series endpoint in scope for this phase (historical candles exist via the backend's `MarketDataProvider`, but no endpoint exposes them to the frontend yet). Leaving a chart wired to fake data would violate this plan's core constraint; removing it is the honest choice until a real historical-candle endpoint exists (future phase).

- [ ] **Step 4: Thread the `instrument` prop in `App.tsx`**

Find the `MARKET_NIFTY` and `MARKET_SENSEX` cases (they currently render `<LevelPanel />` with no props). Check `backend/app/market_data/symbols.py`'s `INDEX_INSTRUMENT_KEYS` for the exact real instrument key strings before writing this — use those exact strings, not `"NIFTY"`/`"SENSEX"`:

```tsx
      case 'MARKET_NIFTY':
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">NIFTY index levels & overview</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5">Comprehensive Spot and derivatives risk analytics</p>
            </div>
            {renderIndexDetailCard('NIFTY')}
            <LevelPanel instrument="NSE_INDEX|Nifty 50" />
          </div>
        );

      case 'MARKET_SENSEX':
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-zinc-100 font-sans font-bold text-lg uppercase tracking-wider">SENSEX index levels & overview</h2>
              <p className="text-xs text-zinc-400 font-sans mt-0.5">Comprehensive Spot and derivatives risk analytics</p>
            </div>
            {renderIndexDetailCard('SENSEX')}
            <LevelPanel instrument="BSE_INDEX|SENSEX" />
          </div>
        );
```

(Verify these exact literal strings against `backend/app/market_data/symbols.py` before committing — do not guess if they differ from what's shown here.)

- [ ] **Step 5: Manual verification**

Confirm both Market pages fetch `/api/v1/levels/{the real instrument key}` (check network tab for the exact URL-encoded instrument string) and show the honest empty state (no levels exist yet without a live feed running long enough to close several candles).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/live.ts frontend/src/hooks/useLiveLevels.ts frontend/src/components/LevelPanel.tsx frontend/src/App.tsx
git commit -m "feat: wire LevelPanel to the real support/resistance engine"
```

---

### Task 7: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the complete backend suite**

Run: `cd backend && python -m pytest -q`
Expected: no new failures beyond the same 3 pre-existing unrelated ones from the Global Constraints baseline.

- [ ] **Step 2: Run the frontend suite**

Run: `cd frontend && npm test`
Expected: all existing tests pass (this plan doesn't touch `usePortfolioStore` or its test, so `portfolioStore.test.ts` should be unaffected).

- [ ] **Step 3: Manual smoke check in the browser**

Start backend + frontend. Navigate to Positions, Orders, and both Market (NIFTY/SENSEX) pages. Confirm: no console errors, each page makes real network requests to the endpoints named above, and each shows either real data or an honest empty state — never a hardcoded number.

- [ ] **Step 4: If any regression is found, fix it and re-run Steps 1-3.**

- [ ] **Step 5: Final commit if fixes were needed — otherwise this closes the phase.**
