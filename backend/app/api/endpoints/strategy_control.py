"""Per-strategy START/STOP, execution_mode (ALGO/PAPER/DISABLED), and
trading_mode (AUTO/MANUAL) control surface for the Algo Dashboard.

This is the API layer over strategy_runtime.py's canonical state. START
performs real readiness checks (broker, market data, risk/execution
engines running, OFAO's data-provenance rule) before flipping a strategy
to RUNNING — it never just changes the frontend toggle. STOP only ever
sets enabled=False (blocking NEW entries via RiskEngine's per-strategy
gate); it never touches an existing open position.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.api.endpoints.strategies import all_registered_strategy_ids, get_registered_strategy
from backend.app.core.active_broker import active_broker
from backend.app.engines.execution import execution_engine
from backend.app.engines.risk import risk_engine
from backend.app.engines.strategy_runtime import ExecutionMode, TradingMode, strategy_runtime
from backend.app.order_flow.footprint_processor import footprint_processor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/strategy-control", tags=["strategy-control"])

# cas_dislocation and OFAO publish DECISION_CREATED directly (bypassing
# STRATEGY_SIGNAL -> OpportunityEngine, so they never get a threaded-through
# strategy_id — see opportunity.py/decision.py) and are gated in RiskEngine
# via their OWN pre-existing config objects (cas_config_state,
# ofao_engine.config), not strategy_runtime's generic strategy_id gate.
# Writing through to those here keeps this dashboard's start/stop as the
# ONE control surface rather than a second, disconnected switch that could
# drift from what actually gates their decisions.
def _sync_legacy_engine_enabled(strategy_id: str, enabled: bool) -> None:
    if strategy_id == "cas_dislocation":
        from backend.app.strategies.cas_dislocation.config_state import cas_config_state
        cas_config_state.enable() if enabled else cas_config_state.disable()
    elif strategy_id == "ofao":
        from backend.app.strategies.order_flow_absorption.engine import ofao_engine
        ofao_engine.enable() if enabled else ofao_engine.disable()
    elif strategy_id == "two_candle":
        from backend.app.strategies.two_candle_engine import two_candle_engine
        two_candle_engine.enable() if enabled else two_candle_engine.disable()
    elif strategy_id == "three_minute_gap":
        from backend.app.strategies.three_minute_gap.engine import three_minute_gap_engine
        three_minute_gap_engine.enable() if enabled else three_minute_gap_engine.disable()


class ExecutionModeRequest(BaseModel):
    mode: ExecutionMode


class TradingModeRequest(BaseModel):
    mode: TradingMode


def _has_open_position(strategy_id: str) -> bool:
    meta = get_registered_strategy(strategy_id)
    engine = meta.get("engine") if meta else None
    if engine is None:
        return False
    if hasattr(engine, "state_machine") and hasattr(engine.state_machine, "active_setups"):
        return bool(engine.state_machine.active_setups())
    if hasattr(engine, "positions"):
        try:
            return any(p and p.get("is_active") for p in engine.positions.values())
        except Exception:
            return False
    return False


def _readiness_checks(strategy_id: str, execution_mode: str, trading_mode: str) -> List[Dict[str, Any]]:
    """Returns an ordered list of {name, passed, reason} — mirrors the
    exact checklist in the spec (strategy exists, config exists, active
    broker, market data, required strategy data, risk engine, execution
    engine, global trading permission). Market session / position
    reconciliation aren't hard-gated today (no generic hook exists for
    either across all 9 engines) — included as informational passes
    rather than fabricating a check that doesn't actually verify anything.
    """
    checks: List[Dict[str, Any]] = []
    meta = get_registered_strategy(strategy_id)

    checks.append({"name": "Strategy exists", "passed": meta is not None,
                    "reason": None if meta else f"{strategy_id} is not a registered strategy."})
    if meta is None:
        return checks

    engine = meta.get("engine")
    # Not every strategy engine has a `.config` object at all (e.g.
    # trending_oi_price_action, straddle) — only fail this check when the
    # engine DOES declare a config attribute but it's falsy/unset, not
    # merely because the attribute doesn't exist.
    config_declared = engine is not None and hasattr(engine, "config")
    config_ok = (not config_declared) or bool(getattr(engine, "config", None))
    checks.append({"name": "Strategy configuration", "passed": config_ok,
                    "reason": None if config_ok else "Strategy engine has no configuration loaded."})

    broker_id = active_broker.get_active_broker_id()
    broker_ready = broker_id is not None and active_broker.is_broker_ready(broker_id)
    checks.append({"name": "Active broker", "passed": broker_ready,
                    "reason": None if broker_ready else "No active, ready broker connection."})

    provider = active_broker.get_active_provider()
    checks.append({"name": "Market data", "passed": provider is not None,
                    "reason": None if provider is not None else "No active market-data provider."})

    checks.append({"name": "Risk engine", "passed": risk_engine._started,
                    "reason": None if risk_engine._started else "Risk engine is not running."})

    checks.append({"name": "Execution engine", "passed": execution_engine._started,
                    "reason": None if execution_engine._started else "Execution engine is not running."})

    # OFAO's hard data-provenance rule — spec requires this to block
    # ALGO+AUTO unconditionally (RiskEngine's own gate only blocks once
    # LIVE is actually armed; this is the stricter start-time check).
    if strategy_id == "ofao" and execution_mode == "ALGO" and trading_mode == "AUTO":
        data_ok = footprint_processor.data_source == "REAL"
        checks.append({"name": "Required strategy data", "passed": data_ok,
                        "reason": None if data_ok else "Real order-flow data unavailable."})
    else:
        checks.append({"name": "Required strategy data", "passed": True, "reason": None})

    checks.append({"name": "Market session", "passed": True, "reason": None})
    checks.append({"name": "Position reconciliation", "passed": True, "reason": None})

    # Global trading permission: whether an ALGO+AUTO decision can ever
    # reach a real broker is governed entirely by the EXISTING LIVE arm
    # switch (execution_runtime_state, /api/v1/execution/arm) — this is
    # informational only, not a second kill switch. PAPER/MANUAL never
    # reach a real broker regardless (force_dry_run / rejected pre-
    # execution), so this check always passes for them.
    checks.append({"name": "Global trading permission", "passed": True, "reason": None})

    return checks


@router.get("")
def list_runtime_states():
    return {sid: s.to_dict() for sid, s in strategy_runtime.get_all().items()}


@router.get("/{strategy_id}")
def get_runtime_state(strategy_id: str):
    if get_registered_strategy(strategy_id) is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return strategy_runtime.get(strategy_id).to_dict()


@router.get("/{strategy_id}/readiness")
def get_readiness(strategy_id: str):
    if get_registered_strategy(strategy_id) is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    state = strategy_runtime.get(strategy_id)
    checks = _readiness_checks(strategy_id, state.execution_mode, state.trading_mode)
    return {"strategy_id": strategy_id, "checks": checks, "all_passed": all(c["passed"] for c in checks)}


@router.post("/{strategy_id}/execution-mode")
def set_execution_mode(strategy_id: str, req: ExecutionModeRequest):
    """execution_mode is a single canonical field — setting it to ALGO
    structurally disables PAPER (and vice versa), enforced by construction
    (one enum field, never two independent booleans)."""
    if get_registered_strategy(strategy_id) is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return strategy_runtime.set_execution_mode(strategy_id, req.mode).to_dict()


@router.post("/{strategy_id}/trading-mode")
def set_trading_mode(strategy_id: str, req: TradingModeRequest):
    if get_registered_strategy(strategy_id) is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    return strategy_runtime.set_trading_mode(strategy_id, req.mode).to_dict()


@router.post("/{strategy_id}/start")
def start_strategy(strategy_id: str):
    if get_registered_strategy(strategy_id) is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")

    state = strategy_runtime.get(strategy_id)
    if state.execution_mode == "DISABLED":
        raise HTTPException(
            status_code=400,
            detail="Select ALGO TRADE or PAPER TRADE before starting (execution_mode is DISABLED).",
        )

    checks = _readiness_checks(strategy_id, state.execution_mode, state.trading_mode)
    failed = [c for c in checks if not c["passed"]]
    if failed:
        reason = "; ".join(f"{c['name']}: {c['reason']}" for c in failed)
        strategy_runtime.mark_blocked(strategy_id, reason)
        raise HTTPException(status_code=409, detail=reason)

    result = strategy_runtime.mark_started(strategy_id)
    _sync_legacy_engine_enabled(strategy_id, True)
    logger.info("Strategy %s started (execution_mode=%s, trading_mode=%s)",
                strategy_id, state.execution_mode, state.trading_mode)
    return result.to_dict()


@router.post("/{strategy_id}/stop")
def stop_strategy(strategy_id: str):
    """STOP only blocks NEW entries (enabled=False, read by RiskEngine's
    per-strategy gate). An existing open position is never touched here —
    it stays under the strategy's own exit-management logic, exactly like
    OFAO's disable() and CAS Dislocation's exit-monitoring-runs-regardless
    rule."""
    if get_registered_strategy(strategy_id) is None:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")

    has_position = _has_open_position(strategy_id)
    result = strategy_runtime.mark_stopped(strategy_id, has_open_position=has_position)
    _sync_legacy_engine_enabled(strategy_id, False)
    logger.info("Strategy %s stopped (open_position=%s)", strategy_id, has_position)
    return result.to_dict()


@router.post("/start-all")
def start_all():
    """Individual per-strategy readiness validation — one blocked strategy
    never fails the others."""
    results = {}
    for strategy_id in all_registered_strategy_ids():
        state = strategy_runtime.get(strategy_id)
        if state.execution_mode == "DISABLED":
            results[strategy_id] = {"started": False, "reason": "execution_mode is DISABLED."}
            continue
        checks = _readiness_checks(strategy_id, state.execution_mode, state.trading_mode)
        failed = [c for c in checks if not c["passed"]]
        if failed:
            reason = "; ".join(f"{c['name']}: {c['reason']}" for c in failed)
            strategy_runtime.mark_blocked(strategy_id, reason)
            results[strategy_id] = {"started": False, "reason": reason}
        else:
            strategy_runtime.mark_started(strategy_id)
            _sync_legacy_engine_enabled(strategy_id, True)
            results[strategy_id] = {"started": True, "reason": None}
    return results


@router.post("/stop-all")
def stop_all():
    """Prevents new entries across every strategy; never closes existing
    positions."""
    results = {}
    for strategy_id in all_registered_strategy_ids():
        has_position = _has_open_position(strategy_id)
        strategy_runtime.mark_stopped(strategy_id, has_open_position=has_position)
        _sync_legacy_engine_enabled(strategy_id, False)
        results[strategy_id] = {"stopped": True, "open_position": has_position}
    return results
