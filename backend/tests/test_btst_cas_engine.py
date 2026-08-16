from datetime import datetime, time
from unittest.mock import patch

import pytest

from backend.app.strategies import btst_cas_engine as btst_cas_engine_module
from backend.app.strategies.btst_cas_engine import BTSTCASEngine, evaluate_btst_signal


class _FixedDateTime(datetime):
    """Stand-in for datetime.now() so evaluate_btst_signal's timing gate
    can be exercised deterministically — the function calls
    datetime.now().time() directly, so freezing the module's `datetime`
    is the only way to control it without a real-time-dependent test.
    """
    _fixed: datetime = datetime(2024, 1, 1, 12, 0)

    @classmethod
    def now(cls, tz=None):
        return cls._fixed


def _at(hh: int, mm: int):
    _FixedDateTime._fixed = datetime(2024, 1, 1, hh, mm)
    return patch.object(btst_cas_engine_module, "datetime", _FixedDateTime)


BULLISH_POST_1PM_OI = {"call_oi_change": 0, "put_oi_change": 0}
BEARISH_POST_1PM_OI = {"call_oi_change": 3_000_000, "put_oi_change": -1_500_000}

MID_CLOSE_CAS = {"equilibrium_price": 105.0, "day_high": 110.0, "day_low": 90.0}
BOTTOM_CLOSE_CAS = {"equilibrium_price": 91.5, "day_high": 110.0, "day_low": 90.0}  # (91.5-90)/20 = 7.5% <= 15%


# --------------------------- timing gate ---------------------------

def test_before_window_returns_waiting():
    with _at(15, 0):
        result = evaluate_btst_signal("SHORT_BUILDUP", BEARISH_POST_1PM_OI, BOTTOM_CLOSE_CAS)
    assert result["status"] == "WAITING"
    assert result["signal"] == "NONE"


def test_after_window_returns_waiting():
    with _at(15, 45):
        result = evaluate_btst_signal("SHORT_BUILDUP", BEARISH_POST_1PM_OI, BOTTOM_CLOSE_CAS)
    assert result["status"] == "WAITING"


def test_inside_window_boundaries_are_active():
    with _at(15, 35):
        result = evaluate_btst_signal("SHORT_BUILDUP", BEARISH_POST_1PM_OI, BOTTOM_CLOSE_CAS)
    assert result["status"] == "ACTIVE_WINDOW"


# --------------------------- pillar logic (inside window) ---------------------------

def test_all_three_pillars_bearish_executes_btst_put():
    with _at(15, 37):
        result = evaluate_btst_signal("SHORT_BUILDUP", BEARISH_POST_1PM_OI, BOTTOM_CLOSE_CAS)
    assert result["signal"] == "EXECUTE_BTST_PUT"
    assert result["pillar_macro"] and result["pillar_micro"] and result["pillar_cas"]


def test_long_unwinding_also_counts_as_macro_bearish():
    with _at(15, 37):
        result = evaluate_btst_signal("LONG_UNWINDING", BEARISH_POST_1PM_OI, BOTTOM_CLOSE_CAS)
    assert result["pillar_macro"] is True
    assert result["signal"] == "EXECUTE_BTST_PUT"


def test_bullish_futures_trend_blocks_signal_despite_other_pillars():
    with _at(15, 37):
        result = evaluate_btst_signal("LONG_BUILDUP", BEARISH_POST_1PM_OI, BOTTOM_CLOSE_CAS)
    assert result["pillar_macro"] is False
    assert result["signal"] == "NEUTRAL"


def test_weak_oi_shift_blocks_micro_pillar():
    with _at(15, 37):
        result = evaluate_btst_signal("SHORT_BUILDUP", BULLISH_POST_1PM_OI, BOTTOM_CLOSE_CAS)
    assert result["pillar_micro"] is False
    assert result["signal"] == "NEUTRAL"


def test_close_away_from_day_low_blocks_cas_pillar():
    with _at(15, 37):
        result = evaluate_btst_signal("SHORT_BUILDUP", BEARISH_POST_1PM_OI, MID_CLOSE_CAS)
    assert result["pillar_cas"] is False
    assert result["signal"] == "NEUTRAL"


def test_flat_day_range_never_counts_as_closing_low():
    flat_range = {"equilibrium_price": 100.0, "day_high": 100.0, "day_low": 100.0}
    with _at(15, 37):
        result = evaluate_btst_signal("SHORT_BUILDUP", BEARISH_POST_1PM_OI, flat_range)
    assert result["pillar_cas"] is False


# --------------------------- BTSTCASEngine lifecycle ---------------------------

@pytest.mark.asyncio
async def test_engine_start_is_idempotent():
    engine = BTSTCASEngine()
    engine.start()
    task = engine._task
    engine.start()  # second call should be a no-op, not spawn a second task
    assert engine._task is task
    engine.stop()


@pytest.mark.asyncio
async def test_engine_publishes_insufficient_data_while_no_data_source_is_wired():
    engine = BTSTCASEngine()
    published = []

    async def _fake_publish(channel, payload):
        published.append((channel, payload))
        engine.stop()  # stop after first publish so the loop doesn't run forever

    with patch.object(btst_cas_engine_module.event_bus, "publish", side_effect=_fake_publish):
        engine.start()
        for _ in range(50):
            if published:
                break
            import asyncio
            await asyncio.sleep(0.2)

    assert published
    channel, payload = published[0]
    assert channel == "btst_cas_stream"
    assert payload["status"] == "INSUFFICIENT_DATA"
    assert payload["signal"] == "NONE"
