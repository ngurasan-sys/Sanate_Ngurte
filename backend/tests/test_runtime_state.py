from backend.app.execution.runtime_state import ExecutionRuntimeState


def test_starts_disarmed():
    state = ExecutionRuntimeState()
    assert state.is_armed() is False
    snap = state.snapshot()
    assert snap.armed is False
    assert snap.armed_at is None


def test_arm_sets_armed_with_timestamp_and_note():
    state = ExecutionRuntimeState()
    snap = state.arm(note="pre-market check done")
    assert state.is_armed() is True
    assert snap.armed is True
    assert snap.armed_at is not None
    assert snap.note == "pre-market check done"


def test_disarm_clears_everything():
    state = ExecutionRuntimeState()
    state.arm(note="x")
    snap = state.disarm()
    assert state.is_armed() is False
    assert snap.armed is False
    assert snap.armed_at is None
    assert snap.note is None
