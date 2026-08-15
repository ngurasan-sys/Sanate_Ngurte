import json
from datetime import datetime, timezone

from backend.app.api.live_stream_adapters import (
    adapt_oh_ol,
    adapt_trending_oi_price_action,
)
from backend.app.strategies.oh_ol.oh_ol_strategy import OhOlStrategy, TargetState


def test_adapt_trending_oi_price_action_valid_state():
    state = {
        "time_filter_status": "VALID",
        "distance_filter_status": "VALID",
        "rejection_reason": "",
        "position_state": "WAITING",
        "lots_held": 0,
        "avg_entry_price": 0.0,
        "current_sl": 0.0,
        "diff_oi_pct": 45.0,
        "indicator_distance": 5.0,
        "supertrend": object(),  # non-serializable, must be dropped
        "daily_atr": object(),   # non-serializable, must be dropped
    }

    risk_status, payload = adapt_trending_oi_price_action(state)

    assert risk_status == [
        {"name": "TIME_FILTER", "passed": True, "rejection_reason": None},
        {"name": "DISTANCE_FILTER", "passed": True, "rejection_reason": None},
    ]
    assert payload["position_state"] == "WAITING"
    assert payload["diff_oi_pct"] == 45.0
    assert "supertrend" not in payload
    assert "daily_atr" not in payload


def test_adapt_trending_oi_price_action_blocked_state():
    state = {
        "time_filter_status": "BLOCKED",
        "distance_filter_status": "VALID",
        "rejection_reason": "REJECTED: Post 2:30 PM Premium Decay Risk",
        "position_state": "TRADE_BLOCKED",
        "lots_held": 0,
        "avg_entry_price": 0.0,
        "current_sl": 0.0,
        "diff_oi_pct": 10.0,
        "indicator_distance": 2.0,
        "supertrend": object(),
        "daily_atr": object(),
    }

    risk_status, payload = adapt_trending_oi_price_action(state)

    assert risk_status[0] == {
        "name": "TIME_FILTER",
        "passed": False,
        "rejection_reason": "REJECTED: Post 2:30 PM Premium Decay Risk",
    }
    assert risk_status[1]["passed"] is True


def test_adapt_oh_ol_no_active_target():
    engine = OhOlStrategy()
    risk_status, payload = adapt_oh_ol(engine, "NIFTY")
    assert risk_status == []
    assert payload == {"status": "NO_ACTIVE_INSTRUMENT_STATE"}


def test_adapt_oh_ol_probability_below_threshold():
    engine = OhOlStrategy()
    target = TargetState(
        instrument="NIFTY",
        option_type="FUT",
        target_type="OH",
        target_price=24000.0,
        detected_at=datetime(2026, 1, 1, 9, 20, tzinfo=timezone.utc),
        active=True,
        consumed=False,
        probability=60.0,
        oi_shift=0.0,
    )
    engine.targets.append(target)

    risk_status, payload = adapt_oh_ol(engine, "NIFTY")

    assert risk_status[0]["name"] == "OPENING_PROBABILITY"
    assert risk_status[0]["passed"] is False
    assert "60.0" in risk_status[0]["rejection_reason"]
    assert risk_status[1]["name"] == "OI_SHIFT_CONFIRMATION"
    assert risk_status[1]["passed"] is False
    assert payload["instrument"] == "NIFTY"


def test_adapt_oh_ol_both_pillars_pass():
    engine = OhOlStrategy()
    target = TargetState(
        instrument="NIFTY",
        option_type="FUT",
        target_type="OH",
        target_price=24000.0,
        detected_at=datetime(2026, 1, 1, 9, 20, tzinfo=timezone.utc),
        active=True,
        consumed=False,
        probability=95.0,
        oi_shift=600000.0,
    )
    engine.targets.append(target)

    risk_status, payload = adapt_oh_ol(engine, "NIFTY")

    assert risk_status[0]["passed"] is True
    assert risk_status[0]["rejection_reason"] is None
    assert risk_status[1]["passed"] is True
    assert risk_status[1]["rejection_reason"] is None


def test_adapt_trending_oi_price_action_sanitizes_inf_defaults():
    # Mirrors the REAL defaults set by _get_instrument_state
    # (backend/app/strategies/trending_oi_price_action/engine.py:42-71), i.e.
    # the exact state that exists at/near market open before the first
    # candle is processed.
    state = {
        "position_state": "WAITING",
        "avg_entry_price": 0.0,
        "lots_held": 0,
        "resistance_rejections": 0,
        "resistance_level": None,
        "false_breakout": False,
        "last_swing_high": None,
        "current_sl": 0.0,
        "indicator_distance": 0.0,
        "bullish_oi_confirmed": False,
        "bearish_oi_confirmed": False,
        "diff_oi_pct": 0.0,
        "strength_dots": 0,
        "last_vwap": 0.0,
        "supertrend": object(),
        "daily_atr": object(),
        "current_day_high": -float("inf"),
        "current_day_low": float("inf"),
        "current_day_str": "",
        "trade_valid": True,
        "rejection_reason": "",
        "time_filter_status": "VALID",
        "distance_filter_status": "VALID",
        "vwap_supertrend_distance": 0.0,
        "tier_1_status": "PENDING",
        "tier_2_status": "PENDING",
        "tier_3_status": "PENDING",
        "partial_exit_done": False,
        "breakeven_done": False,
    }

    risk_status, payload = adapt_trending_oi_price_action(state)

    assert payload["current_day_high"] is None
    assert payload["current_day_low"] is None
    assert "supertrend" not in payload
    assert "daily_atr" not in payload

    serialized = json.dumps(payload)
    assert "Infinity" not in serialized
    assert json.loads(serialized)["current_day_high"] is None
    assert json.loads(serialized)["current_day_low"] is None


def test_adapt_oh_ol_ignores_consumed_or_inactive_targets():
    engine = OhOlStrategy()
    engine.targets.append(TargetState(
        instrument="NIFTY", option_type="FUT", target_type="OH", target_price=24000.0,
        detected_at=datetime(2026, 1, 1, 9, 20, tzinfo=timezone.utc),
        active=True, consumed=True, probability=95.0, oi_shift=600000.0,
    ))
    engine.targets.append(TargetState(
        instrument="NIFTY", option_type="FUT", target_type="OL", target_price=23900.0,
        detected_at=datetime(2026, 1, 1, 9, 20, tzinfo=timezone.utc),
        active=False, consumed=False, probability=95.0, oi_shift=-600000.0,
    ))

    risk_status, payload = adapt_oh_ol(engine, "NIFTY")
    assert risk_status == []
    assert payload == {"status": "NO_ACTIVE_INSTRUMENT_STATE"}
