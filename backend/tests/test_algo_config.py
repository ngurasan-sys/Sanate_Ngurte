import pytest

from backend.app.engines.algo_config import AlgoConfigError, AlgoConfigState


def test_default_state_is_system_disabled():
    state = AlgoConfigState()
    config = state.get()
    assert config.mode == "SYSTEM"
    assert config.enabled is False
    assert config.capital is None
    assert config.lot_schedule == []


def test_configure_system_mode_needs_no_extras():
    state = AlgoConfigState()
    config = state.configure(mode="SYSTEM")
    assert config.mode == "SYSTEM"
    assert config.enabled is False
    assert config.underlying is None
    assert config.capital is None
    assert config.lot_schedule == []


def test_configure_manual_mode_success():
    state = AlgoConfigState()
    config = state.configure(
        mode="MANUAL", underlying="NIFTY", capital=100000.0,
        lot_schedule=[2, 3, 5], stop_loss_pct=30.0, target_pct=50.0,
    )
    assert config.mode == "MANUAL"
    assert config.underlying == "NIFTY"
    assert config.capital == 100000.0
    assert config.lot_schedule == [2, 3, 5]
    assert config.stop_loss_pct == 30.0
    assert config.target_pct == 50.0
    assert config.enabled is False  # configuring never auto-enables
    assert config.updated_at is not None


def test_configure_manual_mode_requires_underlying():
    state = AlgoConfigState()
    with pytest.raises(AlgoConfigError, match="underlying"):
        state.configure(mode="MANUAL", capital=100000.0, lot_schedule=[2])


def test_configure_manual_mode_requires_positive_capital():
    state = AlgoConfigState()
    with pytest.raises(AlgoConfigError, match="capital"):
        state.configure(mode="MANUAL", underlying="NIFTY", capital=0, lot_schedule=[2])
    with pytest.raises(AlgoConfigError, match="capital"):
        state.configure(mode="MANUAL", underlying="NIFTY", capital=-5, lot_schedule=[2])


def test_configure_manual_mode_requires_lot_schedule():
    state = AlgoConfigState()
    with pytest.raises(AlgoConfigError, match="pyramid tier"):
        state.configure(mode="MANUAL", underlying="NIFTY", capital=1000.0, lot_schedule=[])


def test_configure_manual_mode_rejects_non_positive_tier():
    state = AlgoConfigState()
    with pytest.raises(AlgoConfigError, match="positive number of lots"):
        state.configure(mode="MANUAL", underlying="NIFTY", capital=1000.0, lot_schedule=[2, 0, 3])


def test_configure_manual_mode_rejects_non_positive_pct():
    state = AlgoConfigState()
    with pytest.raises(AlgoConfigError, match="stop_loss_pct"):
        state.configure(mode="MANUAL", underlying="NIFTY", capital=1000.0, lot_schedule=[1], stop_loss_pct=0)
    with pytest.raises(AlgoConfigError, match="target_pct"):
        state.configure(mode="MANUAL", underlying="NIFTY", capital=1000.0, lot_schedule=[1], target_pct=-10)


def test_enable_and_disable():
    state = AlgoConfigState()
    state.configure(mode="MANUAL", underlying="NIFTY", capital=1000.0, lot_schedule=[1])
    assert state.get().enabled is False

    state.enable()
    assert state.get().enabled is True

    state.disable()
    assert state.get().enabled is False


def test_reconfiguring_always_disarms():
    state = AlgoConfigState()
    state.configure(mode="MANUAL", underlying="NIFTY", capital=1000.0, lot_schedule=[1])
    state.enable()
    assert state.get().enabled is True

    state.configure(mode="MANUAL", underlying="NIFTY", capital=2000.0, lot_schedule=[2])
    assert state.get().enabled is False
    assert state.get().capital == 2000.0


def test_switching_to_system_clears_manual_fields():
    state = AlgoConfigState()
    state.configure(mode="MANUAL", underlying="NIFTY", capital=1000.0, lot_schedule=[1, 2])
    state.configure(mode="SYSTEM")
    config = state.get()
    assert config.underlying is None
    assert config.capital is None
    assert config.lot_schedule == []
