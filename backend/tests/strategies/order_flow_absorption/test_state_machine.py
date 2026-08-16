from datetime import datetime, timedelta, timezone

import pytest

from backend.app.strategies.order_flow_absorption.models import SetupDirection, SetupState, generate_setup_id
from backend.app.strategies.order_flow_absorption.state_machine import (
    InvalidTransitionError, OFAOStateMachine,
)

NOW = datetime(2026, 8, 16, 9, 48, 12, tzinfo=timezone.utc)


def test_generate_setup_id_matches_spec_format():
    setup_id = generate_setup_id("NIFTY", NOW, SetupDirection.BULL, 1)
    assert setup_id == "NIFTY_2026-08-16_094812_BULL_001"


def test_fresh_instrument_starts_at_no_setup():
    sm = OFAOStateMachine()
    ctx = sm.get("NIFTY FUT")
    assert ctx.state == SetupState.NO_SETUP
    assert sm.has_active_setup("NIFTY FUT") is False


def test_transition_to_location_reached_mints_a_setup_id():
    sm = OFAOStateMachine()
    ctx = sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, now=NOW, direction=SetupDirection.BULL, location_price=25000.0)
    assert ctx.setup_id == "NIFTY_2026-08-16_094812_BULL_001"
    assert ctx.state == SetupState.LOCATION_REACHED
    assert sm.has_active_setup("NIFTY FUT") is True


def test_location_reached_without_direction_raises():
    sm = OFAOStateMachine()
    with pytest.raises(ValueError):
        sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, now=NOW)


def test_setup_id_stable_across_the_rest_of_the_setups_lifecycle():
    sm = OFAOStateMachine()
    sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, now=NOW, direction=SetupDirection.BULL, location_price=25000.0)
    setup_id_at_location = sm.get("NIFTY FUT").setup_id

    sm.transition("NIFTY FUT", SetupState.ABSORPTION_DETECTED, now=NOW, absorption_strength=85.0)
    assert sm.get("NIFTY FUT").setup_id == setup_id_at_location

    sm.transition("NIFTY FUT", SetupState.WAITING_FOR_DOMINANCE, now=NOW)
    sm.transition("NIFTY FUT", SetupState.DOMINANCE_CONFIRMED, now=NOW)
    sm.transition("NIFTY FUT", SetupState.SIGNAL_READY, now=NOW)
    assert sm.get("NIFTY FUT").setup_id == setup_id_at_location


def test_invalid_transition_raises_and_does_not_mutate_state():
    sm = OFAOStateMachine()
    with pytest.raises(InvalidTransitionError):
        sm.transition("NIFTY FUT", SetupState.SIGNAL_READY, now=NOW)  # can't jump straight there
    assert sm.get("NIFTY FUT").state == SetupState.NO_SETUP


def test_cannot_start_a_second_setup_while_one_is_active():
    sm = OFAOStateMachine()
    sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, now=NOW, direction=SetupDirection.BULL, location_price=25000.0)
    assert sm.has_active_setup("NIFTY FUT") is True
    # Engine-level guard: has_active_setup must be checked before ever
    # calling transition(..., LOCATION_REACHED, ...) again — the state
    # machine itself won't allow NO_SETUP-only transitions from a non-terminal state.
    with pytest.raises(InvalidTransitionError):
        sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, now=NOW, direction=SetupDirection.BEAR, location_price=100.0)


def test_reset_only_allowed_from_terminal_states():
    sm = OFAOStateMachine()
    sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, now=NOW, direction=SetupDirection.BULL, location_price=25000.0)
    with pytest.raises(InvalidTransitionError):
        sm.reset("NIFTY FUT", reason="premature")


def test_reset_from_terminal_state_returns_to_no_setup():
    sm = OFAOStateMachine()
    sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, now=NOW, direction=SetupDirection.BULL, location_price=25000.0)
    sm.transition("NIFTY FUT", SetupState.INVALIDATED, now=NOW)
    ctx = sm.reset("NIFTY FUT", reason="thesis invalidated")
    assert ctx.state == SetupState.NO_SETUP
    assert ctx.setup_id is None
    assert sm.has_active_setup("NIFTY FUT") is False


def test_instruments_are_tracked_independently():
    sm = OFAOStateMachine()
    sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, now=NOW, direction=SetupDirection.BULL, location_price=25000.0)
    assert sm.get("SENSEX FUT").state == SetupState.NO_SETUP
    assert sm.has_active_setup("SENSEX FUT") is False


def test_setup_id_sequence_increments_within_the_same_day():
    sm = OFAOStateMachine()
    sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, now=NOW, direction=SetupDirection.BULL, location_price=25000.0)
    sm.transition("NIFTY FUT", SetupState.INVALIDATED, now=NOW)
    sm.reset("NIFTY FUT", reason="done")
    later = NOW + timedelta(minutes=10)
    ctx2 = sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, now=later, direction=SetupDirection.BEAR, location_price=24800.0)
    assert ctx2.setup_id.endswith("_002")


def test_is_signal_stale_false_before_timeout():
    sm = OFAOStateMachine()
    sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, now=NOW, direction=SetupDirection.BULL, location_price=25000.0)
    sm.transition("NIFTY FUT", SetupState.ABSORPTION_DETECTED, now=NOW)
    sm.transition("NIFTY FUT", SetupState.WAITING_FOR_DOMINANCE, now=NOW)
    sm.transition("NIFTY FUT", SetupState.DOMINANCE_CONFIRMED, now=NOW)
    sm.transition("NIFTY FUT", SetupState.SIGNAL_READY, now=NOW)
    soon = NOW + timedelta(seconds=5)
    assert sm.is_signal_stale("NIFTY FUT", timeout_seconds=30, now=soon) is False


def test_is_signal_stale_true_after_timeout():
    sm = OFAOStateMachine()
    sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, now=NOW, direction=SetupDirection.BULL, location_price=25000.0)
    sm.transition("NIFTY FUT", SetupState.ABSORPTION_DETECTED, now=NOW)
    sm.transition("NIFTY FUT", SetupState.WAITING_FOR_DOMINANCE, now=NOW)
    sm.transition("NIFTY FUT", SetupState.DOMINANCE_CONFIRMED, now=NOW)
    sm.transition("NIFTY FUT", SetupState.SIGNAL_READY, now=NOW)
    later = NOW + timedelta(seconds=60)
    assert sm.is_signal_stale("NIFTY FUT", timeout_seconds=30, now=later) is True


def test_is_signal_stale_false_when_not_in_signal_ready_state():
    sm = OFAOStateMachine()
    assert sm.is_signal_stale("NIFTY FUT", timeout_seconds=30, now=NOW) is False


def test_full_happy_path_lifecycle():
    sm = OFAOStateMachine()
    sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, now=NOW, direction=SetupDirection.BULL, location_price=25000.0)
    sm.transition("NIFTY FUT", SetupState.ABSORPTION_DETECTED, now=NOW, absorption_strength=91.0)
    sm.transition("NIFTY FUT", SetupState.WAITING_FOR_DOMINANCE, now=NOW)
    sm.transition("NIFTY FUT", SetupState.DOMINANCE_CONFIRMED, now=NOW)
    sm.transition("NIFTY FUT", SetupState.SIGNAL_READY, now=NOW)
    sm.transition("NIFTY FUT", SetupState.ORDER_SUBMITTED, now=NOW)
    sm.transition("NIFTY FUT", SetupState.ORDER_FILLED, now=NOW)
    sm.transition("NIFTY FUT", SetupState.POSITION_ACTIVE, now=NOW)
    sm.transition("NIFTY FUT", SetupState.TARGET_1, now=NOW)
    sm.transition("NIFTY FUT", SetupState.TARGET_2, now=NOW)
    ctx = sm.transition("NIFTY FUT", SetupState.EXITED, now=NOW)
    assert ctx.state == SetupState.EXITED
    reset_ctx = sm.reset("NIFTY FUT", reason="trade complete")
    assert reset_ctx.state == SetupState.NO_SETUP


def test_has_any_active_setup_false_when_all_no_setup():
    sm = OFAOStateMachine()
    sm.get("NIFTY FUT")
    assert sm.has_any_active_setup() is False


def test_has_any_active_setup_true_when_one_instrument_in_flight():
    sm = OFAOStateMachine()
    sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, direction=SetupDirection.BULL, location_price=100.0)
    assert sm.has_any_active_setup() is True


def test_active_setups_lists_only_in_flight_instruments():
    sm = OFAOStateMachine()
    sm.get("BANKNIFTY FUT")  # touched but never started -> NO_SETUP
    sm.transition("NIFTY FUT", SetupState.LOCATION_REACHED, direction=SetupDirection.BULL, location_price=100.0)
    sm.transition("SENSEX FUT", SetupState.LOCATION_REACHED, direction=SetupDirection.BEAR, location_price=200.0)
    sm.transition("SENSEX FUT", SetupState.INVALIDATED)  # terminal

    assert sm.active_setups() == ["NIFTY FUT"]
    assert sm.has_any_active_setup() is True


def test_active_setups_empty_when_nothing_in_flight():
    sm = OFAOStateMachine()
    sm.get("NIFTY FUT")
    assert sm.active_setups() == []
    assert sm.has_any_active_setup() is False
