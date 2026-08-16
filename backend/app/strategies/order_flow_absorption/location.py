"""Location Engine — spec §4. Determines whether price sits at a
meaningful bullish/bearish location, using the volume profile (§2/§8/§9,
volume_profile.py — new this session, nothing to reuse), Fibonacci
(fibonacci.py), and VWAP (existing, market_data/processor.py's
Candle.vwap — see the architecture doc's caveat that it's currently
inert on the live feed since that feed carries no volume).

VWAP is explicitly never sufficient on its own (spec §3/§4: "VWAP is
contextual confirmation... do not use VWAP alone as a signal") — a
location is only "bullish"/"bearish" if at least one non-VWAP factor
also matches; VWAP proximity can join the matched-factor list but never
carries a location by itself.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from .fibonacci import FibonacciLevels, is_price_in_fib_zone
from .volume_profile import VolumeProfile

DEFAULT_PROXIMITY_PCT = 0.001  # 0.1% of price — "near" a level


@dataclass
class LocationResult:
    is_bullish_location: bool
    is_bearish_location: bool
    is_middle_of_value: bool
    matched_bullish_factors: List[str] = field(default_factory=list)
    matched_bearish_factors: List[str] = field(default_factory=list)


def _near(price: float, level: Optional[float], proximity_pct: float) -> bool:
    if level is None:
        return False
    return abs(price - level) <= abs(price) * proximity_pct


def evaluate_location(
    price: float,
    current_profile: Optional[VolumeProfile] = None,
    previous_profile: Optional[VolumeProfile] = None,
    previous_day_high: Optional[float] = None,
    previous_day_low: Optional[float] = None,
    swing_high: Optional[float] = None,
    swing_low: Optional[float] = None,
    fib_discount: Optional[FibonacciLevels] = None,
    fib_premium: Optional[FibonacciLevels] = None,
    vwap: Optional[float] = None,
    proximity_pct: float = DEFAULT_PROXIMITY_PCT,
    allow_middle_of_value_override: bool = False,
) -> LocationResult:
    bullish_factors: List[str] = []
    bearish_factors: List[str] = []

    # --- Bullish candidate factors ---
    if previous_profile and _near(price, previous_profile.val, proximity_pct):
        bullish_factors.append("previous_val")
    if current_profile and _near(price, current_profile.val, proximity_pct):
        bullish_factors.append("current_val")
    if _near(price, previous_day_low, proximity_pct):
        bullish_factors.append("previous_day_low")
    if _near(price, swing_low, proximity_pct):
        bullish_factors.append("swing_low")
    if current_profile:
        for lvn in current_profile.lvn:
            if _near(price, lvn, proximity_pct):
                bullish_factors.append("lvn")
                break
    if fib_discount and is_price_in_fib_zone(price, fib_discount, proximity_pct):
        bullish_factors.append("fib_discount")
    vwap_near = _near(price, vwap, proximity_pct)
    if vwap_near:
        bullish_factors.append("vwap")

    # --- Bearish candidate factors (mirror) ---
    if previous_profile and _near(price, previous_profile.vah, proximity_pct):
        bearish_factors.append("previous_vah")
    if current_profile and _near(price, current_profile.vah, proximity_pct):
        bearish_factors.append("current_vah")
    if _near(price, previous_day_high, proximity_pct):
        bearish_factors.append("previous_day_high")
    if _near(price, swing_high, proximity_pct):
        bearish_factors.append("swing_high")
    if current_profile:
        for lvn in current_profile.lvn:
            if _near(price, lvn, proximity_pct):
                bearish_factors.append("lvn")
                break
    if fib_premium and is_price_in_fib_zone(price, fib_premium, proximity_pct):
        bearish_factors.append("fib_premium")
    if vwap_near:
        bearish_factors.append("vwap")

    # VWAP alone never counts — at least one other factor must also match.
    non_vwap_bullish = [f for f in bullish_factors if f != "vwap"]
    non_vwap_bearish = [f for f in bearish_factors if f != "vwap"]
    is_bullish = len(non_vwap_bullish) > 0
    is_bearish = len(non_vwap_bearish) > 0

    # --- Middle of value ---
    is_middle = False
    if current_profile and current_profile.val is not None and current_profile.vah is not None:
        near_val_edge = _near(price, current_profile.val, proximity_pct)
        near_vah_edge = _near(price, current_profile.vah, proximity_pct)
        inside_value = current_profile.val < price < current_profile.vah
        if inside_value and not near_val_edge and not near_vah_edge:
            is_middle = True
    if current_profile and _near(price, current_profile.poc, proximity_pct):
        is_middle = True

    if is_middle and not allow_middle_of_value_override:
        # Default: NO TRADE near POC / middle of value overrides any
        # matched factor, per spec §4.
        is_bullish = False
        is_bearish = False

    return LocationResult(
        is_bullish_location=is_bullish,
        is_bearish_location=is_bearish,
        is_middle_of_value=is_middle,
        matched_bullish_factors=bullish_factors,
        matched_bearish_factors=bearish_factors,
    )
