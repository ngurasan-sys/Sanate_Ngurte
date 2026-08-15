import pytest

from backend.app.strategies.cas_dislocation.config_state import CASConfigState
from backend.app.strategies.cas_dislocation.models import CASConfigError


def test_default_state_is_nifty_disabled():
    state = CASConfigState()
    config = state.get()
    assert config.underlying == "NIFTY"
    assert config.enabled is False
    assert config.auto_execute is False


def test_configure_success():
    state = CASConfigState()
    config = state.configure(underlying="SENSEX", lots=2, max_hold_seconds=60, min_score_to_alert=50, min_score_to_execute=90, auto_execute=True)
    assert config.underlying == "SENSEX"
    assert config.lots == 2
    assert config.max_hold_seconds == 60
    assert config.min_score_to_alert == 50
    assert config.min_score_to_execute == 90
    assert config.auto_execute is True
    assert config.enabled is False  # configuring never auto-enables
    assert config.updated_at is not None


def test_configure_rejects_unsupported_underlying():
    state = CASConfigState()
    with pytest.raises(CASConfigError, match="Unsupported underlying"):
        state.configure(underlying="FINNIFTY", lots=1)


def test_configure_rejects_non_positive_lots():
    state = CASConfigState()
    with pytest.raises(CASConfigError, match="lots"):
        state.configure(underlying="NIFTY", lots=0)


def test_configure_rejects_non_positive_max_hold():
    state = CASConfigState()
    with pytest.raises(CASConfigError, match="max_hold_seconds"):
        state.configure(underlying="NIFTY", lots=1, max_hold_seconds=0)


def test_configure_rejects_out_of_range_scores():
    state = CASConfigState()
    with pytest.raises(CASConfigError, match="between 0 and 100"):
        state.configure(underlying="NIFTY", lots=1, min_score_to_alert=-5)
    with pytest.raises(CASConfigError, match="between 0 and 100"):
        state.configure(underlying="NIFTY", lots=1, min_score_to_execute=150)


def test_configure_rejects_execute_threshold_below_alert_threshold():
    state = CASConfigState()
    with pytest.raises(CASConfigError, match="min_score_to_execute must be >= min_score_to_alert"):
        state.configure(underlying="NIFTY", lots=1, min_score_to_alert=80, min_score_to_execute=50)


def test_enable_disable_and_reconfigure_disarms():
    state = CASConfigState()
    state.configure(underlying="NIFTY", lots=1)
    state.enable()
    assert state.get().enabled is True

    state.disable()
    assert state.get().enabled is False

    state.enable()
    state.configure(underlying="BANKNIFTY", lots=2)
    assert state.get().enabled is False
    assert state.get().underlying == "BANKNIFTY"
