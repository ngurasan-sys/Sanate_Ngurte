from typing import Any, Dict, List, Optional, Tuple

RiskStatus = List[Dict[str, Any]]
ActiveStrategyPayload = Dict[str, Any]

_NON_SERIALIZABLE_STATE_KEYS = ("supertrend", "daily_atr")


def adapt_trending_oi_price_action(state: Dict[str, Any]) -> Tuple[RiskStatus, ActiveStrategyPayload]:
    time_valid = state.get("time_filter_status") == "VALID"
    distance_valid = state.get("distance_filter_status") == "VALID"
    rejection_reason = state.get("rejection_reason") or None

    risk_status: RiskStatus = [
        {
            "name": "TIME_FILTER",
            "passed": time_valid,
            "rejection_reason": None if time_valid else rejection_reason,
        },
        {
            "name": "DISTANCE_FILTER",
            "passed": distance_valid,
            "rejection_reason": None if distance_valid else rejection_reason,
        },
    ]

    active_strategy_payload = {
        key: value
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
