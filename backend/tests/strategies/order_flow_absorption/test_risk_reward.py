import pytest

from backend.app.strategies.order_flow_absorption.risk_reward import (
    compute_stop, compute_risk_reward_plan,
)


def test_compute_stop_bull_is_below_defended_price():
    stop = compute_stop(defended_price=25000.0, direction="BULL", buffer_pct=0.001)
    assert stop < 25000.0
    assert stop == pytest.approx(24975.0)


def test_compute_stop_bear_is_above_defended_price():
    stop = compute_stop(defended_price=25000.0, direction="BEAR", buffer_pct=0.001)
    assert stop > 25000.0
    assert stop == pytest.approx(25025.0)


def test_risk_reward_plan_bull_default_1_5r():
    plan = compute_risk_reward_plan(entry=25010.0, stop=24970.0, direction="BULL")
    assert plan.risk_points == pytest.approx(40.0)
    assert plan.target == pytest.approx(25010.0 + 40.0 * 1.5)
    assert plan.risk_reward == pytest.approx(1.5)
    assert plan.target_source == "1.5R"


def test_risk_reward_plan_bear_default_1_5r():
    plan = compute_risk_reward_plan(entry=25000.0, stop=25040.0, direction="BEAR")
    assert plan.risk_points == pytest.approx(40.0)
    assert plan.target == pytest.approx(25000.0 - 60.0)
    assert plan.risk_reward == pytest.approx(1.5)


def test_risk_reward_plan_uses_structural_target_when_further_than_r_multiple():
    plan = compute_risk_reward_plan(entry=25010.0, stop=24970.0, direction="BULL", structural_target=25100.0)
    assert plan.target == 25100.0
    assert plan.target_source == "structural"
    assert plan.risk_reward > 1.5


def test_risk_reward_plan_ignores_structural_target_when_it_shrinks_reward():
    # structural target closer than the 1.5R floor -> must not be used
    plan = compute_risk_reward_plan(entry=25010.0, stop=24970.0, direction="BULL", structural_target=25020.0)
    assert plan.target_source == "1.5R"
    assert plan.risk_reward == pytest.approx(1.5)


def test_risk_reward_plan_rejects_stop_on_wrong_side_for_bull():
    with pytest.raises(ValueError):
        compute_risk_reward_plan(entry=25000.0, stop=25010.0, direction="BULL")


def test_risk_reward_plan_rejects_stop_on_wrong_side_for_bear():
    with pytest.raises(ValueError):
        compute_risk_reward_plan(entry=25000.0, stop=24990.0, direction="BEAR")


def test_risk_reward_plan_rejects_zero_risk():
    with pytest.raises(ValueError):
        compute_risk_reward_plan(entry=25000.0, stop=25000.0, direction="BULL")
