"""Proves strategy_runtime's generic per-strategy gate actually blocks
RiskEngine.process_decision when a strategy is stopped/disabled, that
ALGO/PAPER execution_mode are mutually exclusive by construction, that
MANUAL trading_mode blocks automatic order submission, and that PAPER
forces DRY_RUN at the execution boundary regardless of the global LIVE
arm switch. Mirrors test_ofao_risk_gate.py's structure.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from backend.app.engines.risk import RiskEngine
from backend.app.engines.strategy_runtime import StrategyRuntimeRegistry
from backend.app.execution.risk_limits import RiskLimits

GENEROUS_LIMITS = RiskLimits(max_quantity_per_order=10000)


@pytest.fixture
def runtime(monkeypatch):
    """A fresh, isolated registry per test — never touches the real
    .strategy_runtime.json on disk."""
    fresh = StrategyRuntimeRegistry()
    fresh._loaded = True  # skip disk load entirely
    monkeypatch.setattr(fresh, "_persist", lambda: None)  # no disk writes in tests
    monkeypatch.setattr("backend.app.engines.risk.strategy_runtime", fresh)
    return fresh


def _decision(**kw):
    d = {
        "decision_id": "DEC_TEST_001",
        "instrument": "NIFTY 25000 CE",
        "instrument_token": "NSE_FO|1",
        "action": "TRADE",
        "quantity": 65,
        "price": 100.0,
        "transaction_type": "BUY",
        "timestamp": datetime(2026, 1, 1, 11, 0),
        # Deliberately NOT "ALGO"/"CAS_DISLOCATION"/"OFAO" — those sources
        # have their own dedicated gates (see test_algo_risk_gate.py etc).
        # Using a source RiskEngine doesn't special-case isolates these
        # tests to strategy_runtime's NEW generic strategy_id gate only.
        "source": "STRATEGY",
        "strategy_id": "gap_opening_strategies",
    }
    d.update(kw)
    return d


async def _run(engine, decision):
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    with patch("backend.app.engines.risk.event_bus.publish", new=capture), \
         patch("backend.app.engines.risk.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 1, 11, 0)
        await engine.process_decision(decision)

    return published


class TestExecutionModeMutualExclusivity:
    def test_execution_mode_is_a_single_field_not_two_booleans(self, runtime):
        state = runtime.set_execution_mode("gap_opening_strategies", "ALGO")
        assert state.execution_mode == "ALGO"
        state = runtime.set_execution_mode("gap_opening_strategies", "PAPER")
        # Setting PAPER structurally replaces ALGO — there is no way to
        # represent "both ALGO and PAPER" since it's one enum field.
        assert state.execution_mode == "PAPER"

    def test_setting_disabled_also_clears_enabled_flag(self, runtime):
        runtime.mark_started("gap_opening_strategies")
        assert runtime.get("gap_opening_strategies").enabled is True
        state = runtime.set_execution_mode("gap_opening_strategies", "DISABLED")
        assert state.enabled is False
        assert state.status == "OFF"


class TestTradingModeMutualExclusivity:
    def test_trading_mode_is_a_single_field(self, runtime):
        state = runtime.set_trading_mode("gap_opening_strategies", "AUTO")
        assert state.trading_mode == "AUTO"
        state = runtime.set_trading_mode("gap_opening_strategies", "MANUAL")
        assert state.trading_mode == "MANUAL"


class TestRiskEngineGate:
    @pytest.mark.asyncio
    async def test_decision_rejected_when_strategy_never_started(self, runtime):
        # execution_mode/trading_mode default DISABLED/AUTO, enabled=False
        runtime.set_execution_mode("gap_opening_strategies", "ALGO")
        engine = RiskEngine(GENEROUS_LIMITS)
        published = await _run(engine, _decision())

        assert "EXECUTION_REQUEST" not in [t for t, _ in published]
        risk_decision = next(p for t, p in published if t == "RISK_DECISION")
        assert "not enabled" in risk_decision["reason"]

    @pytest.mark.asyncio
    async def test_decision_approved_once_algo_auto_started(self, runtime):
        runtime.set_execution_mode("gap_opening_strategies", "ALGO")
        runtime.set_trading_mode("gap_opening_strategies", "AUTO")
        runtime.mark_started("gap_opening_strategies")
        engine = RiskEngine(GENEROUS_LIMITS)
        published = await _run(engine, _decision())

        assert "EXECUTION_REQUEST" in [t for t, _ in published]

    @pytest.mark.asyncio
    async def test_stopping_blocks_new_entries(self, runtime):
        runtime.set_execution_mode("gap_opening_strategies", "ALGO")
        runtime.mark_started("gap_opening_strategies")
        runtime.mark_stopped("gap_opening_strategies", has_open_position=False)
        engine = RiskEngine(GENEROUS_LIMITS)
        published = await _run(engine, _decision())

        assert "EXECUTION_REQUEST" not in [t for t, _ in published]

    @pytest.mark.asyncio
    async def test_stopping_with_open_position_still_blocks_new_entries(self, runtime):
        """STOP never touches an existing position, but it must still
        block NEW entries — verifying the gate doesn't accidentally treat
        POSITION_ACTIVE as 'still running, allow new decisions'."""
        runtime.set_execution_mode("gap_opening_strategies", "ALGO")
        runtime.mark_started("gap_opening_strategies")
        state = runtime.mark_stopped("gap_opening_strategies", has_open_position=True)

        assert state.status == "POSITION_ACTIVE"
        assert state.enabled is False

        engine = RiskEngine(GENEROUS_LIMITS)
        published = await _run(engine, _decision())
        assert "EXECUTION_REQUEST" not in [t for t, _ in published]

    @pytest.mark.asyncio
    async def test_manual_trading_mode_blocks_automatic_order_submission(self, runtime):
        runtime.set_execution_mode("gap_opening_strategies", "ALGO")
        runtime.set_trading_mode("gap_opening_strategies", "MANUAL")
        runtime.mark_started("gap_opening_strategies")
        engine = RiskEngine(GENEROUS_LIMITS)
        published = await _run(engine, _decision())

        assert "EXECUTION_REQUEST" not in [t for t, _ in published]
        risk_decision = next(p for t, p in published if t == "RISK_DECISION")
        assert "MANUAL trading mode" in risk_decision["reason"]
        # The decision (signal) is still published for UI visibility, even
        # though it's rejected for auto-execution.
        assert any(t == "RISK_DECISION" for t, _ in published)

    @pytest.mark.asyncio
    async def test_paper_execution_mode_forces_dry_run_flag_on_request(self, runtime):
        runtime.set_execution_mode("gap_opening_strategies", "PAPER")
        runtime.set_trading_mode("gap_opening_strategies", "AUTO")
        runtime.mark_started("gap_opening_strategies")
        engine = RiskEngine(GENEROUS_LIMITS)
        published = await _run(engine, _decision())

        exec_req = next(p for t, p in published if t == "EXECUTION_REQUEST")
        assert exec_req["force_dry_run"] is True

    @pytest.mark.asyncio
    async def test_algo_execution_mode_does_not_force_dry_run(self, runtime):
        runtime.set_execution_mode("gap_opening_strategies", "ALGO")
        runtime.set_trading_mode("gap_opening_strategies", "AUTO")
        runtime.mark_started("gap_opening_strategies")
        engine = RiskEngine(GENEROUS_LIMITS)
        published = await _run(engine, _decision())

        exec_req = next(p for t, p in published if t == "EXECUTION_REQUEST")
        assert exec_req["force_dry_run"] is False

    @pytest.mark.asyncio
    async def test_decision_without_strategy_id_is_ungated_legacy_behavior(self, runtime):
        """Strategies never touched via the new dashboard controls keep
        working exactly as before this feature existed — no strategy_id on
        the decision means no per-strategy gate is applied."""
        engine = RiskEngine(GENEROUS_LIMITS)
        published = await _run(engine, _decision(strategy_id=None))

        assert "EXECUTION_REQUEST" in [t for t, _ in published]


class TestPersistence:
    def test_state_persists_across_registry_instances(self, tmp_path, monkeypatch):
        state_file = tmp_path / ".strategy_runtime.json"
        monkeypatch.setattr("backend.app.engines.strategy_runtime.STATE_PATH", state_file)

        first = StrategyRuntimeRegistry()
        first.set_execution_mode("gap_opening_strategies", "ALGO")
        first.set_trading_mode("gap_opening_strategies", "MANUAL")
        first.mark_started("gap_opening_strategies")

        # Simulates a backend restart: brand-new registry instance reading
        # the same on-disk file.
        second = StrategyRuntimeRegistry()
        state = second.get("gap_opening_strategies")

        assert state.execution_mode == "ALGO"
        assert state.trading_mode == "MANUAL"
        assert state.enabled is True
        assert state.status == "RUNNING"
