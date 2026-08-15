import math
from typing import Any, Dict, List, Optional, Tuple

RiskStatus = List[Dict[str, Any]]
ActiveStrategyPayload = Dict[str, Any]

_NON_SERIALIZABLE_STATE_KEYS = ("supertrend", "daily_atr")


def _sanitize_json_value(value: Any) -> Any:
    """Replace non-finite floats (inf/-inf/nan) with None.

    The websocket transport (``websocket.send_json`` -> Starlette) serializes
    with ``allow_nan=True``, so a non-finite float does NOT raise here: it is
    emitted as the bare literal ``Infinity`` / ``-Infinity`` / ``NaN``. Those
    are not valid JSON, so a browser/JS client's ``JSON.parse`` rejects the
    entire frame outright — a silent, total loss of the message rather than a
    server-side error we would see. Sanitizing keeps every frame parseable.
    """
    if isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
        return None
    return value


def sanitize_payload(value: Any) -> Any:
    """Recursively apply :func:`_sanitize_json_value` across a whole payload.

    Applied once at the real JSON boundary (the assembled payload just before
    it is sent) so no individual field-computation site has to remember to
    sanitize itself.
    """
    if isinstance(value, dict):
        return {key: sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_payload(item) for item in value]
    return _sanitize_json_value(value)


# The engine keeps a single shared `rejection_reason` field, and the distance
# filter only overwrites it while `trade_valid` is still True. So when the time
# filter has already blocked, a subsequently-blocked distance filter carries the
# TIME_FILTER's text — attributing a wrong reason to the distance pillar. Each
# pillar therefore reports its own static, pillar-specific reason instead.
_TIME_FILTER_REASON = "Outside valid trading time window"
_DISTANCE_FILTER_REASON = "VWAP/SuperTrend distance exceeds threshold"


def adapt_trending_oi_price_action(state: Dict[str, Any]) -> Tuple[RiskStatus, ActiveStrategyPayload]:
    time_valid = state.get("time_filter_status") == "VALID"
    distance_valid = state.get("distance_filter_status") == "VALID"

    risk_status: RiskStatus = [
        {
            "name": "TIME_FILTER",
            "passed": time_valid,
            "rejection_reason": None if time_valid else _TIME_FILTER_REASON,
        },
        {
            "name": "DISTANCE_FILTER",
            "passed": distance_valid,
            "rejection_reason": None if distance_valid else _DISTANCE_FILTER_REASON,
        },
    ]

    active_strategy_payload = {
        key: _sanitize_json_value(value)
        for key, value in state.items()
        if key not in _NON_SERIALIZABLE_STATE_KEYS
    }

    return risk_status, active_strategy_payload


def adapt_oh_ol(engine, instrument: str) -> Tuple[RiskStatus, ActiveStrategyPayload]:
    target = next(
        (t for t in engine.targets if t.instrument == instrument and t.active and not t.consumed),
        None,
    )

    if target is None:
        return [], {"status": "NO_ACTIVE_INSTRUMENT_STATE"}

    probability_passed = target.probability >= engine.opening_prob_threshold
    probability_reason: Optional[str] = None
    if not probability_passed:
        probability_reason = (
            f"Probability {target.probability:.1f} below {engine.opening_prob_threshold} threshold"
        )

    if target.target_type == "OH":
        oi_confirmed = target.oi_shift >= engine.min_oi_shift
    else:
        oi_confirmed = target.oi_shift <= -engine.min_oi_shift
    oi_reason: Optional[str] = None
    if not oi_confirmed:
        oi_reason = (
            f"OI shift {target.oi_shift} has not crossed the {engine.min_oi_shift} confirmation threshold"
        )

    risk_status: RiskStatus = [
        {"name": "OPENING_PROBABILITY", "passed": probability_passed, "rejection_reason": probability_reason},
        {"name": "OI_SHIFT_CONFIRMATION", "passed": oi_confirmed, "rejection_reason": oi_reason},
    ]

    active_strategy_payload = target.model_dump(mode="json")

    return risk_status, active_strategy_payload
