"""Verifies _readiness_checks' 'Strategy configuration' check against the
ACTUAL 9 registered strategy engines' real .config shapes, not just the
fake stand-in engine used in test_strategy_control_api.py. Guards against
a regression like the one caught during development: engines with no
.config attribute at all (trending_oi_price_action, intraday_trend_scalper,
oh_ol, straddle, pullback_chop_filter, cas_dislocation) must trivially
pass rather than being flagged as "no configuration loaded".
"""

import pytest

from backend.app.api.endpoints.strategy_control import _readiness_checks
from backend.app.strategies.cas_dislocation.engine import cas_dislocation_engine
from backend.app.strategies.expiry_reversal.engine import expiry_reversal_engine
from backend.app.strategies.gap_opening.engine import gap_opening_engine
from backend.app.strategies.intraday_trend_scalper.engine import intraday_trend_scalper
from backend.app.strategies.oh_ol import oh_ol_strategy
from backend.app.strategies.order_flow_absorption.engine import ofao_engine
from backend.app.strategies.pullback_chop_filter.engine import pullback_chop_filter_engine
from backend.app.strategies.straddle.straddle_engine import straddle_engine
from backend.app.strategies.trending_oi_price_action.engine import trending_oi_pa_engine


REAL_ENGINES = {
    "gap_opening_strategies": gap_opening_engine,
    "expiry_reversal": expiry_reversal_engine,
    "ofao": ofao_engine,
    "trending_oi_price_action": trending_oi_pa_engine,
    "intraday_trend_scalper": intraday_trend_scalper,
    "oh_ol": oh_ol_strategy,
    "straddle": straddle_engine,
    "pullback_chop_filter": pullback_chop_filter_engine,
    "cas_dislocation": cas_dislocation_engine,
}


@pytest.mark.parametrize("strategy_id,engine", list(REAL_ENGINES.items()))
def test_strategy_configuration_check_passes_for_real_engine(strategy_id, engine, monkeypatch):
    from backend.app.api.endpoints import strategies as strategies_module
    monkeypatch.setitem(
        strategies_module._strategy_registry, strategy_id,
        {"id": strategy_id, "name": strategy_id, "description": "", "engine": engine},
    )

    checks = _readiness_checks(strategy_id, "PAPER", "AUTO")
    config_check = next(c for c in checks if c["name"] == "Strategy configuration")

    assert config_check["passed"] is True, (
        f"{strategy_id}'s real engine ({type(engine).__name__}) failed the "
        f"configuration check: {config_check['reason']}"
    )


def test_config_declared_but_falsy_actually_fails():
    """The inverse case — an engine that DOES declare .config but it's
    None/empty should still be flagged, proving the fix isn't a blanket
    always-pass."""
    class _EngineWithEmptyConfig:
        config = None

    checks = _readiness_checks("irrelevant", "PAPER", "AUTO")
    # This uses the registry lookup path, so patch registry directly:
    from backend.app.api.endpoints import strategy_control as sc_module
    from backend.app.api.endpoints import strategies as strategies_module
    strategies_module._strategy_registry["fake_empty_config"] = {
        "id": "fake_empty_config", "name": "x", "description": "", "engine": _EngineWithEmptyConfig(),
    }
    try:
        checks = sc_module._readiness_checks("fake_empty_config", "PAPER", "AUTO")
        config_check = next(c for c in checks if c["name"] == "Strategy configuration")
        assert config_check["passed"] is False
        assert "no configuration loaded" in config_check["reason"]
    finally:
        strategies_module._strategy_registry.pop("fake_empty_config", None)
