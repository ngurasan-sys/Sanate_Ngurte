"""Absorption Engine — spec §6/§7, the core of OFAO.

Built entirely on the existing footprint data (order_flow.footprint_candle
.FootprintCandle — delta, buy_volume, sell_volume, per-price-level
total_volume). No new market-data plumbing, just interpretation logic
that doesn't exist anywhere else in this codebase.

Per spec §7's explicit warning, absorption is NOT "delta below a
threshold" — every function here requires BOTH aggression (elevated
opposing volume/delta) AND failure of price to follow (the defended
level actually holding), never one without the other. `price_failure`
is its own scored component specifically so a strong-delta, level-broken
sequence can't score as absorption just because delta was extreme.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from backend.app.order_flow.footprint_candle import FootprintCandle

DEFAULT_LOCATION_TOLERANCE_PCT = 0.0015
DEFAULT_MIN_CANDLES = 2
DEFAULT_MAX_BREAK_PCT = 0.005  # how far price may exceed the location before "failure" collapses to 0

DEFAULT_WEIGHTS = {
    "delta": 0.25,
    "aggressive_volume": 0.15,
    "price_failure": 0.25,
    "wick": 0.15,
    "repeated_tests": 0.10,
    "volume_concentration": 0.10,
}


@dataclass
class AbsorptionResult:
    detected: bool
    direction: str  # "SELLER_ABSORPTION" | "BUYER_ABSORPTION" | "NONE"
    strength: float  # 0-100
    defended_price: Optional[float]
    repeated_tests: int
    components: Dict[str, float] = field(default_factory=dict)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _delta_score(cumulative_delta: float, want_negative: bool, delta_history: Optional[Sequence[float]], window_total_volume: float) -> float:
    if delta_history and len(delta_history) >= 5:
        mean = sum(delta_history) / len(delta_history)
        variance = sum((d - mean) ** 2 for d in delta_history) / len(delta_history)
        stdev = variance ** 0.5
        if stdev > 0:
            z = (cumulative_delta - mean) / stdev
            z = -z if want_negative else z
            return _clamp((z / 3.0) * 100.0)
    # Fallback with no usable history: magnitude of delta relative to
    # total volume traded in the window (a simple, honest proxy — never
    # fabricates a percentile it doesn't have data for).
    if window_total_volume <= 0:
        return 0.0
    magnitude = abs(cumulative_delta) / window_total_volume
    correct_sign = (cumulative_delta < 0) if want_negative else (cumulative_delta > 0)
    return _clamp(magnitude * 200.0) if correct_sign else 0.0


def _aggressive_volume_score(window_aggressive_volume: float, opposing_volume: float, volume_history: Optional[Sequence[float]]) -> float:
    if volume_history and len(volume_history) >= 5:
        avg = sum(volume_history) / len(volume_history)
        if avg > 0:
            ratio = window_aggressive_volume / avg
            return _clamp((ratio - 1.0) * 50.0)
    ratio = window_aggressive_volume / (opposing_volume + 1.0)
    return _clamp((ratio - 1.0) * 25.0)


def _price_failure_score(location_price: float, defended_price: float, direction: str, max_break_pct: float) -> float:
    """direction="SELLER": defended_price is the window's low; failure to
    extend lower means defended_price should be at/above location_price.
    direction="BUYER": defended_price is the window's high; mirror.
    """
    if direction == "SELLER":
        excursion = location_price - defended_price  # positive means price broke below location
    else:
        excursion = defended_price - location_price
    max_break = abs(location_price) * max_break_pct
    if max_break <= 0:
        return 0.0
    return _clamp(100.0 - (excursion / max_break) * 100.0)


def _wick_score(window_close: float, defended_price: float, window_range: float, direction: str) -> float:
    if window_range <= 0:
        return 50.0  # neutral — no range to judge rejection from
    if direction == "SELLER":
        return _clamp(((window_close - defended_price) / window_range) * 100.0)
    return _clamp(((defended_price - window_close) / window_range) * 100.0)


def _repeated_tests_score(repeated_tests: int) -> float:
    return _clamp((repeated_tests - 1) * 40.0)


def _volume_concentration_score(candles: Sequence[FootprintCandle], defended_price: float, tolerance: float) -> float:
    total = 0
    concentrated = 0
    for c in candles:
        for price, node in c.footprint.items():
            total += node.total_volume
            if abs(price - defended_price) <= tolerance:
                concentrated += node.total_volume
    if total <= 0:
        return 0.0
    return _clamp((concentrated / total) * 100.0)


def _detect_absorption(
    candles: Sequence[FootprintCandle],
    location_price: float,
    direction: str,  # "SELLER" | "BUYER"
    location_tolerance_pct: float,
    min_candles: int,
    max_break_pct: float,
    delta_history: Optional[Sequence[float]],
    volume_history: Optional[Sequence[float]],
    weights: Dict[str, float],
) -> AbsorptionResult:
    tolerance = abs(location_price) * location_tolerance_pct

    if direction == "SELLER":
        near = [c for c in candles if abs(c.low - location_price) <= tolerance or c.low <= location_price + tolerance]
    else:
        near = [c for c in candles if abs(c.high - location_price) <= tolerance or c.high >= location_price - tolerance]

    none_result = AbsorptionResult(
        detected=False, direction="NONE", strength=0.0, defended_price=None, repeated_tests=0,
    )
    if len(near) < min_candles:
        return none_result

    cumulative_delta = sum(c.delta for c in near)
    window_total_volume = sum(c.buy_volume + c.sell_volume for c in near)
    aggressive_volume = sum(c.sell_volume for c in near) if direction == "SELLER" else sum(c.buy_volume for c in near)
    opposing_volume = sum(c.buy_volume for c in near) if direction == "SELLER" else sum(c.sell_volume for c in near)

    defended_price = min(c.low for c in near) if direction == "SELLER" else max(c.high for c in near)
    window_high = max(c.high for c in near)
    window_low = min(c.low for c in near)
    window_range = window_high - window_low
    window_close = near[-1].close

    defend_tolerance = abs(location_price) * location_tolerance_pct
    if direction == "SELLER":
        repeated_tests = sum(1 for c in near if abs(c.low - defended_price) <= defend_tolerance)
    else:
        repeated_tests = sum(1 for c in near if abs(c.high - defended_price) <= defend_tolerance)

    want_negative_delta = direction == "SELLER"
    correct_sign_delta = (cumulative_delta < 0) if want_negative_delta else (cumulative_delta > 0)

    price_held = (
        defended_price >= location_price - abs(location_price) * max_break_pct
        if direction == "SELLER"
        else defended_price <= location_price + abs(location_price) * max_break_pct
    )

    components = {
        "delta": _delta_score(cumulative_delta, want_negative_delta, delta_history, window_total_volume),
        "aggressive_volume": _aggressive_volume_score(aggressive_volume, opposing_volume, volume_history),
        "price_failure": _price_failure_score(location_price, defended_price, direction, max_break_pct),
        "wick": _wick_score(window_close, defended_price, window_range, direction),
        "repeated_tests": _repeated_tests_score(repeated_tests),
        "volume_concentration": _volume_concentration_score(near, defended_price, defend_tolerance),
    }
    strength = sum(components[k] * weights[k] for k in weights)

    detected = correct_sign_delta and price_held and repeated_tests >= 2

    return AbsorptionResult(
        detected=detected,
        direction=(f"{direction}_ABSORPTION" if detected else "NONE"),
        strength=strength,
        defended_price=defended_price,
        repeated_tests=repeated_tests,
        components=components,
    )


def detect_seller_absorption(
    candles: Sequence[FootprintCandle],
    location_price: float,
    location_tolerance_pct: float = DEFAULT_LOCATION_TOLERANCE_PCT,
    min_candles: int = DEFAULT_MIN_CANDLES,
    max_break_pct: float = DEFAULT_MAX_BREAK_PCT,
    delta_history: Optional[Sequence[float]] = None,
    volume_history: Optional[Sequence[float]] = None,
    weights: Dict[str, float] = DEFAULT_WEIGHTS,
) -> AbsorptionResult:
    """Bullish setup: aggressive selling attacks a bullish location and
    fails to extend price lower — SELLER_ABSORPTION.
    """
    return _detect_absorption(
        candles, location_price, "SELLER", location_tolerance_pct, min_candles,
        max_break_pct, delta_history, volume_history, weights,
    )


def detect_buyer_absorption(
    candles: Sequence[FootprintCandle],
    location_price: float,
    location_tolerance_pct: float = DEFAULT_LOCATION_TOLERANCE_PCT,
    min_candles: int = DEFAULT_MIN_CANDLES,
    max_break_pct: float = DEFAULT_MAX_BREAK_PCT,
    delta_history: Optional[Sequence[float]] = None,
    volume_history: Optional[Sequence[float]] = None,
    weights: Dict[str, float] = DEFAULT_WEIGHTS,
) -> AbsorptionResult:
    """Bearish setup: aggressive buying attacks a bearish location and
    fails to extend price higher — BUYER_ABSORPTION.
    """
    return _detect_absorption(
        candles, location_price, "BUYER", location_tolerance_pct, min_candles,
        max_break_pct, delta_history, volume_history, weights,
    )
