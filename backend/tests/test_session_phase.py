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
