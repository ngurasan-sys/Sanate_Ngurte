"""Volume Profile engine: POC, Value Area High/Low, HVN/LVN.

No volume-profile implementation existed anywhere in this codebase before
this module (confirmed via repository-wide search — see
docs/order_flow_option_strategy_architecture.md §8/9). Built here from
scratch, but deliberately reuses the existing footprint data structures
(order_flow.footprint_candle.FootprintCandle/FootprintNode) rather than
recomputing volume-by-price independently — a FootprintCandle already has
exactly what a volume profile needs (total_volume per price level), just
scoped to one candle at a time. This module merges that across however
many candles the caller supplies (one session, one hour, one day —
whatever period the caller wants a profile for) and layers the
POC/value-area/HVN-LVN math on top.

Pure functions, no I/O, no live state — everything here is testable
against synthetic FootprintCandle fixtures.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from backend.app.order_flow.footprint_candle import FootprintCandle

DEFAULT_VALUE_AREA_PCT = 0.68  # the standard "68% of volume" value-area convention


@dataclass
class VolumeProfile:
    poc: Optional[float]
    vah: Optional[float]
    val: Optional[float]
    hvn: List[float]
    lvn: List[float]
    total_volume: int


def build_price_volume_distribution(candles: List[FootprintCandle]) -> Dict[float, int]:
    """Merges total_volume-per-price-level across every candle given —
    the raw input every other function in this module works from.
    """
    distribution: Dict[float, int] = {}
    for candle in candles:
        for price, node in candle.footprint.items():
            distribution[price] = distribution.get(price, 0) + node.total_volume
    return distribution


def compute_poc(distribution: Dict[float, int]) -> Optional[float]:
    """Point of Control: the single price level with the most volume."""
    if not distribution:
        return None
    return max(distribution.items(), key=lambda kv: kv[1])[0]


def compute_value_area(
    distribution: Dict[float, int], value_area_pct: float = DEFAULT_VALUE_AREA_PCT,
) -> Tuple[Optional[float], Optional[float]]:
    """Standard value-area algorithm: start at POC, expand to whichever
    adjacent price level (immediately above or below the current range)
    carries more volume, repeating until value_area_pct of total volume
    is captured. Returns (VAH, VAL).
    """
    if not distribution:
        return None, None

    total = sum(distribution.values())
    if total <= 0:
        return None, None

    sorted_prices = sorted(distribution.keys())
    poc = compute_poc(distribution)
    poc_idx = sorted_prices.index(poc)

    lo = hi = poc_idx
    captured = distribution[sorted_prices[poc_idx]]
    target = total * value_area_pct

    while captured < target:
        below_available = lo - 1 >= 0
        above_available = hi + 1 < len(sorted_prices)
        if not below_available and not above_available:
            break

        below_vol = distribution[sorted_prices[lo - 1]] if below_available else -1
        above_vol = distribution[sorted_prices[hi + 1]] if above_available else -1

        if above_vol >= below_vol:
            hi += 1
            captured += distribution[sorted_prices[hi]]
        else:
            lo -= 1
            captured += distribution[sorted_prices[lo]]

    return sorted_prices[hi], sorted_prices[lo]  # (VAH, VAL)


def find_hvn_lvn(distribution: Dict[float, int]) -> Tuple[List[float], List[float]]:
    """Local maxima (High Volume Nodes) and minima (Low Volume Nodes)
    along the sorted price axis — a price level whose volume exceeds (or
    falls below) both immediate neighbors. The endpoints of the range are
    never classified either way — a local extremum needs neighbors on
    both sides to be meaningful.
    """
    sorted_prices = sorted(distribution.keys())
    hvn: List[float] = []
    lvn: List[float] = []

    for i in range(1, len(sorted_prices) - 1):
        price = sorted_prices[i]
        v = distribution[price]
        left = distribution[sorted_prices[i - 1]]
        right = distribution[sorted_prices[i + 1]]
        if v > left and v > right:
            hvn.append(price)
        elif v < left and v < right:
            lvn.append(price)

    return hvn, lvn


def compute_volume_profile(
    candles: List[FootprintCandle], value_area_pct: float = DEFAULT_VALUE_AREA_PCT,
) -> VolumeProfile:
    """The one entry point callers should use — builds the distribution
    and every derived stat in one call.
    """
    distribution = build_price_volume_distribution(candles)
    poc = compute_poc(distribution)
    vah, val = compute_value_area(distribution, value_area_pct)
    hvn, lvn = find_hvn_lvn(distribution)
    return VolumeProfile(
        poc=poc, vah=vah, val=val, hvn=hvn, lvn=lvn,
        total_volume=sum(distribution.values()),
    )
