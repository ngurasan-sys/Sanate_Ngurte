"""Fibonacci retracement levels from a recent meaningful swing — spec §5.

No Fibonacci calculator exists anywhere in this codebase (repository-wide
search, see architecture doc). These are descriptive price levels only —
per the spec's own instruction, this module makes no claim that they are
predictive; it just computes where they sit.
"""

from dataclasses import dataclass
from typing import Optional

DEFAULT_RETRACEMENT_LEVELS = (0.705, 0.786, 0.886)
DEFAULT_INVALIDATION_LEVEL = 0.886


@dataclass
class FibonacciLevels:
    swing_high: float
    swing_low: float
    direction: str  # "DISCOUNT" (retracement down into an uptrend) | "PREMIUM" (retracement up into a downtrend)
    levels: dict    # {0.705: price, 0.786: price, 0.886: price}
    invalidation_price: float


def compute_retracement_levels(
    swing_high: float,
    swing_low: float,
    direction: str,
    levels: tuple = DEFAULT_RETRACEMENT_LEVELS,
    invalidation_level: float = DEFAULT_INVALIDATION_LEVEL,
) -> FibonacciLevels:
    """direction="DISCOUNT": bullish structure, retracement measured DOWN
    from swing_high toward swing_low (a pullback in an uptrend — the
    "discount" zone bulls look to buy).
    direction="PREMIUM": bearish structure, retracement measured UP from
    swing_low toward swing_high (a pullback in a downtrend — the
    "premium" zone bears look to sell).
    """
    if swing_high <= swing_low:
        raise ValueError(f"swing_high ({swing_high}) must be greater than swing_low ({swing_low}).")
    if direction not in ("DISCOUNT", "PREMIUM"):
        raise ValueError(f"direction must be 'DISCOUNT' or 'PREMIUM', got {direction!r}.")

    span = swing_high - swing_low
    computed = {}
    for pct in levels:
        if direction == "DISCOUNT":
            computed[pct] = swing_high - span * pct
        else:
            computed[pct] = swing_low + span * pct

    invalidation_price = (
        swing_high - span * invalidation_level if direction == "DISCOUNT"
        else swing_low + span * invalidation_level
    )

    return FibonacciLevels(
        swing_high=swing_high, swing_low=swing_low, direction=direction,
        levels=computed, invalidation_price=invalidation_price,
    )


def is_price_in_fib_zone(
    price: float, fib: FibonacciLevels, tolerance_pct: float = 0.001,
) -> bool:
    """True if `price` sits within `tolerance_pct` of any configured
    retracement level (a "confluence" check, not an exact-match one —
    real ticks essentially never land on the level exactly).
    """
    span = fib.swing_high - fib.swing_low
    tolerance = span * tolerance_pct
    return any(abs(price - level_price) <= tolerance for level_price in fib.levels.values())


def is_invalidated(price: float, fib: FibonacciLevels) -> bool:
    """True once price has traded through the invalidation level (default
    88.6%) — the point past which the swing this Fib is drawn from is no
    longer considered valid.
    """
    if fib.direction == "DISCOUNT":
        return price < fib.invalidation_price
    return price > fib.invalidation_price


def closest_level(price: float, fib: FibonacciLevels) -> Optional[float]:
    """Which configured retracement percentage `price` is nearest to —
    useful for reporting ("price is at the 78.6% level"), not for the
    zone check itself (use is_price_in_fib_zone for that).
    """
    if not fib.levels:
        return None
    return min(fib.levels.keys(), key=lambda pct: abs(price - fib.levels[pct]))
