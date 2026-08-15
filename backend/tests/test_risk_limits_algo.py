import pytest

from backend.app.engines.algo_config import AlgoTradingConfig
from backend.app.execution.risk_limits import (
    RiskState,
    check_algo_enabled,
    check_capital_budget,
    check_lot_schedule,
    evaluate_algo_extra,
)


def _config(**kw):
    d = dict(mode="MANUAL", enabled=True, underlying="NIFTY", capital=100000.0, lot_schedule=[2, 3, 5])
    d.update(kw)
    return AlgoTradingConfig(**d)


# --------------------------- check_algo_enabled ---------------------------

def test_check_algo_enabled_blocks_when_disabled():
    assert check_algo_enabled(_config(enabled=False)) is not None


def test_check_algo_enabled_passes_when_enabled():
    assert check_algo_enabled(_config(enabled=True)) is None


# --------------------------- check_capital_budget ---------------------------

def test_capital_budget_none_in_system_mode():
    assert check_capital_budget(_config(mode="SYSTEM"), RiskState(), "NIFTY 24500 CE", 65, 100.0) is None


def test_capital_budget_none_for_different_underlying():
    config = _config(underlying="BANKNIFTY")
    assert check_capital_budget(config, RiskState(), "NIFTY 24500 CE", 65, 100.0) is None


def test_capital_budget_passes_within_budget():
    config = _config(capital=100000.0)
    state = RiskState(capital_deployed_today=0.0)
    # 65 qty * 100 = 6500, well within 100000
    assert check_capital_budget(config, state, "NIFTY 24500 CE", 65, 100.0) is None


def test_capital_budget_rejects_when_exceeded():
    config = _config(capital=5000.0)
    state = RiskState(capital_deployed_today=0.0)
    reason = check_capital_budget(config, state, "NIFTY 24500 CE", 65, 100.0)  # value = 6500 > 5000
    assert reason is not None
    assert "exceeding the configured budget" in reason


def test_capital_budget_accounts_for_already_deployed():
    config = _config(capital=10000.0)
    state = RiskState(capital_deployed_today=8000.0)
    reason = check_capital_budget(config, state, "NIFTY 24500 CE", 65, 50.0)  # 8000 + 3250 = 11250 > 10000
    assert reason is not None


# --------------------------- check_lot_schedule ---------------------------

def test_lot_schedule_none_in_system_mode():
    assert check_lot_schedule(_config(mode="SYSTEM"), RiskState(), "NIFTY 24500 CE", "NSE_FO|1", 65) is None


def test_lot_schedule_none_for_different_underlying():
    config = _config(underlying="BANKNIFTY")
    assert check_lot_schedule(config, RiskState(), "NIFTY 24500 CE", "NSE_FO|1", 65) is None


def test_lot_schedule_first_fill_allows_tier_1():
    config = _config(lot_schedule=[2, 3, 5])  # NIFTY lot size 65 -> tier1 max = 130
    state = RiskState()
    assert check_lot_schedule(config, state, "NIFTY 24500 CE", "NSE_FO|1", 130) is None


def test_lot_schedule_first_fill_rejects_over_tier_1():
    config = _config(lot_schedule=[2, 3, 5])
    state = RiskState()
    reason = check_lot_schedule(config, state, "NIFTY 24500 CE", "NSE_FO|1", 195)  # 3 lots, tier1 allows 2
    assert reason is not None
    assert "Tier 1 allows at most 2 lots" in reason


def test_lot_schedule_second_fill_uses_tier_2():
    config = _config(lot_schedule=[2, 3, 5])
    state = RiskState(fill_count_by_instrument={"NSE_FO|1": 1})  # already had 1 fill
    assert check_lot_schedule(config, state, "NIFTY 24500 CE", "NSE_FO|1", 195) is None  # 3 lots = tier2 max
    reason = check_lot_schedule(config, state, "NIFTY 24500 CE", "NSE_FO|1", 260)  # 4 lots > tier2's 3
    assert reason is not None
    assert "Tier 2 allows at most 3 lots" in reason


def test_lot_schedule_rejects_beyond_configured_tiers():
    config = _config(lot_schedule=[2, 3])
    state = RiskState(fill_count_by_instrument={"NSE_FO|1": 2})  # both tiers used
    reason = check_lot_schedule(config, state, "NIFTY 24500 CE", "NSE_FO|1", 65)
    assert reason is not None
    assert "No pyramid tier configured for fill #3" in reason


def test_lot_schedule_tracks_instruments_independently():
    config = _config(lot_schedule=[2, 3])
    state = RiskState(fill_count_by_instrument={"NSE_FO|1": 2})  # exhausted for CE
    # A different strike/instrument_key starts fresh at tier 1.
    assert check_lot_schedule(config, state, "NIFTY 24600 PE", "NSE_FO|2", 130) is None


# --------------------------- evaluate_algo_extra ---------------------------

def test_evaluate_algo_extra_all_pass():
    config = _config()
    state = RiskState()
    approved, reasons = evaluate_algo_extra(config, state, "NIFTY 24500 CE", "NSE_FO|1", 130, 100.0)
    assert approved is True
    assert reasons == []


def test_evaluate_algo_extra_collects_multiple_reasons():
    config = _config(enabled=False, capital=100.0)  # disabled AND tiny budget
    state = RiskState()
    approved, reasons = evaluate_algo_extra(config, state, "NIFTY 24500 CE", "NSE_FO|1", 130, 1000.0)
    assert approved is False
    assert len(reasons) == 2  # not-enabled + over-budget


def test_evaluate_algo_extra_system_mode_only_checks_enabled():
    config = _config(mode="SYSTEM", enabled=True)
    state = RiskState()
    approved, reasons = evaluate_algo_extra(config, state, "NIFTY 24500 CE", "NSE_FO|1", 999999, 100.0)
    assert approved is True  # capital/lot-schedule don't apply in SYSTEM mode
    assert reasons == []
