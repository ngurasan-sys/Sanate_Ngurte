# Unified Live Stream Websocket Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `GET /ws/live-stream?strategy=<id>&instrument=<key>`, a single websocket endpoint that pushes one aggregated JSON payload per second per client — session phase, per-strategy risk pillar status, active strategy state, and market stats.

**Architecture:** A pure `compute_session_phase()` function, two per-strategy adapter functions that translate existing in-memory engine state into a normalized `risk_status` shape, and a dedicated websocket route (not the existing generic `/ws/{channel}` broadcaster, since each client's payload varies by which strategy/instrument it selects).

**Tech Stack:** FastAPI `WebSocket`, existing `TrendingOIPriceActionStrategy`/`OhOlStrategy` singletons, `pytest` + `pytest-asyncio` + `TestClient.websocket_connect`.

## Global Constraints

- No `heavyweight_alignment_count` anywhere in the payload — dropped per the no-stock-futures decision.
- `risk_status` is not a fixed 4-item list — it reflects whatever filter/pillar state the *selected* strategy already tracks. Only `trending_oi_price_action` and `oh_ol` get real adapters in this plan; `straddle`, `two_candle`, `btst_cas`, `pullback_chop` return `risk_status: []` honestly rather than a fabricated structure.
- Session phase boundaries (exact, reused from existing code for consistency): `< 09:15` → `CLOSED`; `09:15–14:30` → `CONTINUOUS`; `14:30–15:15` → `DECAY`; `15:15–15:35` → `CAS`; `15:35–15:40` → `GOLDEN_WINDOW`; `≥ 15:40` → `CLOSED`.
- `atr_progress_pct` reports `null`, never `0`, when the underlying ATR isn't computable yet (fewer than the needed daily candles) — `0` would misrepresent "not yet computable" as "no range used".
- Unknown `strategy` query value closes the connection at accept time (code 1003) rather than silently defaulting.
- No test may depend on real wall-clock time or a live market feed — session-phase tests pass a `time` object directly; adapter tests feed synthetic engine state; the endpoint test only asserts payload shape, not specific values.
- **Update, superseding the "newly discovered" note this plan originally had:** `gap_opening_engine` (the module-level singleton in `backend/app/strategies/gap_opening/engine.py`) is now wired into `main.py`'s lifespan (started/stopped alongside every other engine) as of commit `07ae4f8`. Its `oi_regime: Dict[str, str]` dict is therefore real, live-updating state — Task 3 reads `regime` from it directly instead of hardcoding `"UNKNOWN"`.

---

## Task 1: Session phase calculator

**Files:**
- Create: `backend/app/api/session_phase.py`
- Test: `backend/tests/test_session_phase.py`

**Interfaces:**
- Produces: `compute_session_phase(now: datetime.time) -> str`, returning one of `"CLOSED"`, `"CONTINUOUS"`, `"DECAY"`, `"CAS"`, `"GOLDEN_WINDOW"`. Task 3 imports and calls this.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_session_phase.py`:

```python
from datetime import time

from backend.app.api.session_phase import compute_session_phase


def test_before_market_open_is_closed():
    assert compute_session_phase(time(9, 14, 59)) == "CLOSED"


def test_market_open_is_continuous():
    assert compute_session_phase(time(9, 15, 0)) == "CONTINUOUS"


def test_just_before_decay_is_continuous():
    assert compute_session_phase(time(14, 29, 59)) == "CONTINUOUS"


def test_decay_starts_at_1430():
    assert compute_session_phase(time(14, 30, 0)) == "DECAY"


def test_just_before_cas_is_decay():
    assert compute_session_phase(time(15, 14, 59)) == "DECAY"


def test_cas_starts_at_1515():
    assert compute_session_phase(time(15, 15, 0)) == "CAS"


def test_just_before_golden_window_is_cas():
    assert compute_session_phase(time(15, 34, 59)) == "CAS"


def test_golden_window_starts_at_1535():
    assert compute_session_phase(time(15, 35, 0)) == "GOLDEN_WINDOW"


def test_just_before_close_is_golden_window():
    assert compute_session_phase(time(15, 39, 59)) == "GOLDEN_WINDOW"


def test_after_1540_is_closed():
    assert compute_session_phase(time(15, 40, 0)) == "CLOSED"


def test_late_night_is_closed():
    assert compute_session_phase(time(23, 0, 0)) == "CLOSED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/sanate && .venv/Scripts/python.exe -m pytest backend/tests/test_session_phase.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.api.session_phase'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/api/session_phase.py`:

```python
from datetime import time


def compute_session_phase(now: time) -> str:
    if now < time(9, 15):
        return "CLOSED"
    if now < time(14, 30):
        return "CONTINUOUS"
    if now < time(15, 15):
        return "DECAY"
    if now < time(15, 35):
        return "CAS"
    if now < time(15, 40):
        return "GOLDEN_WINDOW"
    return "CLOSED"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:/sanate && .venv/Scripts/python.exe -m pytest backend/tests/test_session_phase.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
cd D:/sanate && git add backend/app/api/session_phase.py backend/tests/test_session_phase.py
git commit -m "feat: add session phase calculator for live-stream endpoint"
```

---

## Task 2: Per-strategy risk_status adapters

**Files:**
- Create: `backend/app/api/live_stream_adapters.py`
- Test: `backend/tests/test_live_stream_adapters.py`

**Interfaces:**
- Consumes: `trending_oi_pa_engine.positions[instrument]` dict shape (fields: `time_filter_status`, `distance_filter_status`, `rejection_reason`, `diff_oi_pct`, `strength_dots`, `position_state`, `lots_held`, `avg_entry_price`, `current_sl`, `indicator_distance`, plus non-serializable `supertrend`/`daily_atr` indicator objects — see `backend/app/strategies/trending_oi_price_action/engine.py:40-73`). `OhOlStrategy.targets: List[TargetState]` where `TargetState` (pydantic model, `backend/app/strategies/oh_ol/oh_ol_strategy.py:35-61`) has fields `instrument`, `active`, `consumed`, `target_type` (`"OH"`/`"OL"`), `probability`, `oi_shift`. `OhOlStrategy.opening_prob_threshold` (90.0) and `OhOlStrategy.min_oi_shift` (500000.0) — `backend/app/strategies/oh_ol/oh_ol_strategy.py:76,79`.
- Produces: `adapt_trending_oi_price_action(state: dict) -> tuple[list[dict], dict]` and `adapt_oh_ol(engine: OhOlStrategy, instrument: str) -> tuple[list[dict], dict]`. Each returns `(risk_status, active_strategy_payload)` where `risk_status` is `list[{"name": str, "passed": bool, "rejection_reason": str | None}]` and `active_strategy_payload` is a JSON-serializable dict. Task 3 calls both.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_live_stream_adapters.py`:

```python
from datetime import datetime, timezone

from backend.app.api.live_stream_adapters import (
    adapt_oh_ol,
    adapt_trending_oi_price_action,
)
from backend.app.strategies.oh_ol.oh_ol_strategy import OhOlStrategy, TargetState


def test_adapt_trending_oi_price_action_valid_state():
    state = {
        "time_filter_status": "VALID",
        "distance_filter_status": "VALID",
        "rejection_reason": "",
        "position_state": "WAITING",
        "lots_held": 0,
        "avg_entry_price": 0.0,
        "current_sl": 0.0,
        "diff_oi_pct": 45.0,
        "indicator_distance": 5.0,
        "supertrend": object(),  # non-serializable, must be dropped
        "daily_atr": object(),   # non-serializable, must be dropped
    }

    risk_status, payload = adapt_trending_oi_price_action(state)

    assert risk_status == [
        {"name": "TIME_FILTER", "passed": True, "rejection_reason": None},
        {"name": "DISTANCE_FILTER", "passed": True, "rejection_reason": None},
    ]
    assert payload["position_state"] == "WAITING"
    assert payload["diff_oi_pct"] == 45.0
    assert "supertrend" not in payload
    assert "daily_atr" not in payload


def test_adapt_trending_oi_price_action_blocked_state():
    state = {
        "time_filter_status": "BLOCKED",
        "distance_filter_status": "VALID",
        "rejection_reason": "REJECTED: Post 2:30 PM Premium Decay Risk",
        "position_state": "TRADE_BLOCKED",
        "lots_held": 0,
        "avg_entry_price": 0.0,
        "current_sl": 0.0,
        "diff_oi_pct": 10.0,
        "indicator_distance": 2.0,
        "supertrend": object(),
        "daily_atr": object(),
    }

    risk_status, payload = adapt_trending_oi_price_action(state)

    assert risk_status[0] == {
        "name": "TIME_FILTER",
        "passed": False,
        "rejection_reason": "REJECTED: Post 2:30 PM Premium Decay Risk",
    }
    assert risk_status[1]["passed"] is True


def test_adapt_oh_ol_no_active_target():
    engine = OhOlStrategy()
    risk_status, payload = adapt_oh_ol(engine, "NIFTY")
    assert risk_status == []
    assert payload == {"status": "NO_ACTIVE_INSTRUMENT_STATE"}


def test_adapt_oh_ol_probability_below_threshold():
    engine = OhOlStrategy()
    target = TargetState(
        instrument="NIFTY",
        option_type="FUT",
        target_type="OH",
        target_price=24000.0,
        detected_at=datetime(2026, 1, 1, 9, 20, tzinfo=timezone.utc),
        active=True,
        consumed=False,
        probability=60.0,
        oi_shift=0.0,
    )
    engine.targets.append(target)

    risk_status, payload = adapt_oh_ol(engine, "NIFTY")

    assert risk_status[0]["name"] == "OPENING_PROBABILITY"
    assert risk_status[0]["passed"] is False
    assert "60.0" in risk_status[0]["rejection_reason"]
    assert risk_status[1]["name"] == "OI_SHIFT_CONFIRMATION"
    assert risk_status[1]["passed"] is False
    assert payload["instrument"] == "NIFTY"


def test_adapt_oh_ol_both_pillars_pass():
    engine = OhOlStrategy()
    target = TargetState(
        instrument="NIFTY",
        option_type="FUT",
        target_type="OH",
        target_price=24000.0,
        detected_at=datetime(2026, 1, 1, 9, 20, tzinfo=timezone.utc),
        active=True,
        consumed=False,
        probability=95.0,
        oi_shift=600000.0,
    )
    engine.targets.append(target)

    risk_status, payload = adapt_oh_ol(engine, "NIFTY")

    assert risk_status[0]["passed"] is True
    assert risk_status[0]["rejection_reason"] is None
    assert risk_status[1]["passed"] is True
    assert risk_status[1]["rejection_reason"] is None


def test_adapt_oh_ol_ignores_consumed_or_inactive_targets():
    engine = OhOlStrategy()
    engine.targets.append(TargetState(
        instrument="NIFTY", option_type="FUT", target_type="OH", target_price=24000.0,
        detected_at=datetime(2026, 1, 1, 9, 20, tzinfo=timezone.utc),
        active=True, consumed=True, probability=95.0, oi_shift=600000.0,
    ))
    engine.targets.append(TargetState(
        instrument="NIFTY", option_type="FUT", target_type="OL", target_price=23900.0,
        detected_at=datetime(2026, 1, 1, 9, 20, tzinfo=timezone.utc),
        active=False, consumed=False, probability=95.0, oi_shift=-600000.0,
    ))

    risk_status, payload = adapt_oh_ol(engine, "NIFTY")
    assert risk_status == []
    assert payload == {"status": "NO_ACTIVE_INSTRUMENT_STATE"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/sanate && .venv/Scripts/python.exe -m pytest backend/tests/test_live_stream_adapters.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.api.live_stream_adapters'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/api/live_stream_adapters.py`:

```python
from typing import Any, Dict, List, Optional, Tuple

RiskStatus = List[Dict[str, Any]]
ActiveStrategyPayload = Dict[str, Any]

_NON_SERIALIZABLE_STATE_KEYS = ("supertrend", "daily_atr")


def adapt_trending_oi_price_action(state: Dict[str, Any]) -> Tuple[RiskStatus, ActiveStrategyPayload]:
    time_valid = state.get("time_filter_status") == "VALID"
    distance_valid = state.get("distance_filter_status") == "VALID"
    rejection_reason = state.get("rejection_reason") or None

    risk_status: RiskStatus = [
        {
            "name": "TIME_FILTER",
            "passed": time_valid,
            "rejection_reason": None if time_valid else rejection_reason,
        },
        {
            "name": "DISTANCE_FILTER",
            "passed": distance_valid,
            "rejection_reason": None if distance_valid else rejection_reason,
        },
    ]

    active_strategy_payload = {
        key: value
        for key, value in state.items()
        if key not in _NON_SERIALIZABLE_STATE_KEYS
    }

    return risk_status, active_strategy_payload


def adapt_oh_ol(engine, instrument: str) -> Tuple[RiskStatus, ActiveStrategyPayload]:
    target = next(
        (t for t in engine.targets if t.instrument == instrument and t.active and not t.consumed),
        None,
    )

    if target is None:
        return [], {"status": "NO_ACTIVE_INSTRUMENT_STATE"}

    probability_passed = target.probability >= engine.opening_prob_threshold
    probability_reason: Optional[str] = None
    if not probability_passed:
        probability_reason = (
            f"Probability {target.probability:.1f} below {engine.opening_prob_threshold} threshold"
        )

    if target.target_type == "OH":
        oi_confirmed = target.oi_shift >= engine.min_oi_shift
    else:
        oi_confirmed = target.oi_shift <= -engine.min_oi_shift
    oi_reason: Optional[str] = None
    if not oi_confirmed:
        oi_reason = (
            f"OI shift {target.oi_shift} has not crossed the {engine.min_oi_shift} confirmation threshold"
        )

    risk_status: RiskStatus = [
        {"name": "OPENING_PROBABILITY", "passed": probability_passed, "rejection_reason": probability_reason},
        {"name": "OI_SHIFT_CONFIRMATION", "passed": oi_confirmed, "rejection_reason": oi_reason},
    ]

    active_strategy_payload = target.model_dump(mode="json")

    return risk_status, active_strategy_payload
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:/sanate && .venv/Scripts/python.exe -m pytest backend/tests/test_live_stream_adapters.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
cd D:/sanate && git add backend/app/api/live_stream_adapters.py backend/tests/test_live_stream_adapters.py
git commit -m "feat: add risk_status adapters for trending_oi_price_action and oh_ol"
```

---

## Task 3: `/ws/live-stream` endpoint

**Files:**
- Create: `backend/app/api/endpoints/live_stream.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_live_stream_endpoint.py`

**Interfaces:**
- Consumes: `compute_session_phase` (Task 1), `adapt_trending_oi_price_action`/`adapt_oh_ol` (Task 2), `trending_oi_pa_engine` singleton (`backend.app.strategies.trending_oi_price_action.engine`), `oh_ol_strategy` singleton (`backend.app.strategies.oh_ol`, re-exported from `backend/app/strategies/oh_ol/__init__.py`), `gap_opening_engine.oi_regime: Dict[str, str]` singleton (`backend.app.strategies.gap_opening.engine`, keyed by bare underlying e.g. `"NIFTY"`, populated by `handle_trending_oi` — wired into `main.py`'s lifespan as of commit `07ae4f8`).
- Produces: `router: APIRouter` with the `/ws/live-stream` route, registered in `main.py`. No later task depends on this.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_live_stream_endpoint.py`:

```python
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


def test_live_stream_rejects_unknown_strategy():
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/live-stream?strategy=not_a_real_strategy"):
                pass


def test_live_stream_missing_strategy_param_rejected():
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/live-stream"):
                pass


def test_live_stream_accepts_supported_strategy_and_sends_payload():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live-stream?strategy=trending_oi_price_action") as ws:
            payload = ws.receive_json()

            assert "timestamp" in payload
            assert payload["session_phase"] in {
                "CLOSED", "CONTINUOUS", "DECAY", "CAS", "GOLDEN_WINDOW",
            }
            assert isinstance(payload["risk_status"], list)
            assert isinstance(payload["active_strategy_payload"], dict)
            assert set(payload["market_stats"].keys()) == {
                "regime", "oi_difference_pct", "atr_progress_pct",
            }


def test_live_stream_strategy_without_adapter_reports_empty_risk_status():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live-stream?strategy=straddle") as ws:
            payload = ws.receive_json()
            assert payload["risk_status"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/sanate && .venv/Scripts/python.exe -m pytest backend/tests/test_live_stream_endpoint.py -v --timeout=60`
Expected: FAIL — the first two tests fail because `/ws/live-stream` doesn't exist yet (generic `/ws/{channel}` catches the path and rejects `live-stream` as an unknown channel with the wrong semantics for these assertions to be meaningful long-term, and the last two fail outright since the route isn't registered with a `strategy` query parameter at all).

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/api/endpoints/live_stream.py`:

```python
import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.app.api.live_stream_adapters import adapt_oh_ol, adapt_trending_oi_price_action
from backend.app.api.session_phase import compute_session_phase
from backend.app.strategies.gap_opening.engine import gap_opening_engine
from backend.app.strategies.oh_ol import oh_ol_strategy
from backend.app.strategies.trending_oi_price_action.engine import trending_oi_pa_engine

logger = logging.getLogger(__name__)

router = APIRouter()

SUPPORTED_STRATEGIES = {
    "trending_oi_price_action",
    "oh_ol",
    "straddle",
    "two_candle",
    "btst_cas",
    "pullback_chop",
}

_ADAPTED_STRATEGIES = {"trending_oi_price_action", "oh_ol"}

_DEFAULT_INSTRUMENT = {
    "trending_oi_price_action": "NIFTY FUT",
    "oh_ol": "NIFTY",
}


def _build_payload(strategy: str, instrument: str) -> dict:
    now = datetime.now()
    session_phase = compute_session_phase(now.time())

    risk_status = []
    active_strategy_payload: dict = {}
    diff_oi_pct: Optional[float] = None
    atr_progress_pct: Optional[float] = None
    # gap_opening_engine.oi_regime is keyed by bare underlying ("NIFTY"),
    # not the " FUT"-suffixed instrument keys trending_oi_price_action
    # uses internally — normalize before lookup. Reports "UNKNOWN" only
    # when that underlying genuinely has no OI regime classification yet
    # (e.g. before the first trending_oi tick of the day), not as a
    # permanent placeholder.
    underlying = instrument.replace(" FUT", "")
    regime = gap_opening_engine.oi_regime.get(underlying, "UNKNOWN")

    if strategy == "trending_oi_price_action":
        state = trending_oi_pa_engine.positions.get(instrument)
        if state:
            risk_status, active_strategy_payload = adapt_trending_oi_price_action(state)
            diff_oi_pct = state.get("diff_oi_pct")

            daily_atr = state.get("daily_atr")
            atr_values = getattr(daily_atr, "atr_values", None)
            if atr_values:
                daily_atr_val = atr_values[-1]
                if daily_atr_val:
                    intraday_range = state.get("current_day_high", 0.0) - state.get("current_day_low", 0.0)
                    atr_progress_pct = (intraday_range / daily_atr_val) * 100.0
        else:
            active_strategy_payload = {"status": "NO_ACTIVE_INSTRUMENT_STATE"}
    elif strategy == "oh_ol":
        risk_status, active_strategy_payload = adapt_oh_ol(oh_ol_strategy, instrument)

    return {
        "timestamp": now.isoformat(),
        "session_phase": session_phase,
        "risk_status": risk_status,
        "active_strategy_payload": active_strategy_payload,
        "market_stats": {
            "regime": regime,
            "oi_difference_pct": diff_oi_pct,
            "atr_progress_pct": atr_progress_pct,
        },
    }


@router.websocket("/ws/live-stream")
async def live_stream(websocket: WebSocket, strategy: str = Query(...), instrument: Optional[str] = Query(None)):
    if strategy not in SUPPORTED_STRATEGIES:
        await websocket.close(code=1003, reason=f"Unknown strategy: {strategy}")
        return

    await websocket.accept()
    resolved_instrument = instrument or _DEFAULT_INSTRUMENT.get(strategy, "NIFTY")
    logger.info(f"live-stream client connected (strategy={strategy}, instrument={resolved_instrument})")

    try:
        while True:
            try:
                payload = _build_payload(strategy, resolved_instrument)
                await websocket.send_json(payload)
            except Exception:
                logger.exception("Error building live-stream payload; continuing")
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info(f"live-stream client disconnected (strategy={strategy})")
```

Now wire it into `backend/app/main.py`. Add the import near the other endpoint router imports (after the `algo` import, around line 13):

```python
from backend.app.api.endpoints.algo import router as algo_router
from backend.app.api.endpoints.live_stream import router as live_stream_router
```

And register it near the other `app.include_router(...)` calls (after the `algo_router` registration):

```python
app.include_router(
    algo_router
)

app.include_router(
    live_stream_router
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd D:/sanate && .venv/Scripts/python.exe -m pytest backend/tests/test_live_stream_endpoint.py -v --timeout=60`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full backend suite**

Run: `cd D:/sanate && .venv/Scripts/python.exe -m pytest -q --timeout=60`
Expected: same baseline as before this plan — the same pre-existing unrelated failures (`test_bullish_setup`, `test_full_event_flow`, `test_candle_aggregation_no_look_ahead`), plus this plan's new tests passing, no new failures, no hangs, no collection errors.

- [ ] **Step 6: Commit**

```bash
cd D:/sanate && git add backend/app/api/endpoints/live_stream.py backend/app/main.py backend/tests/test_live_stream_endpoint.py
git commit -m "feat: add unified /ws/live-stream websocket endpoint"
```
