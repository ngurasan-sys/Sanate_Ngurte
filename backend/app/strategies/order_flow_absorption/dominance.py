"""Dominance Shift + microstructure confirmation — spec §8/§9.

After absorption, this module watches the *subsequent* candles for
opposing aggression, a diagonal imbalance at a configurable ratio
(200-500%, default 400%, per spec §8), and a break of the micro swing
formed during absorption — using the footprint's intrabar high/low
rather than only candle close, per spec §9's explicit instruction.

The imbalance check reuses the exact comparison order_flow.analysis
.check_diagonal_imbalance already implements (ask_volume at level X vs
bid_volume at level X-1, and the mirror) — but does NOT call that
function directly, because it mutates FootprintNode objects in place.
Those same FootprintCandle objects are shared with the live footprint
chart's own aggregator (footprint_processor.aggregator) using its own,
independently-configured ratio; overwriting their buy_imbalance/
sell_imbalance flags with OFAO's ratio would corrupt what the footprint
UI displays. So the math is reused, the mutation is not — the same
non-mutating approach the frontend's imbalance.ts already takes for the
identical reason (an individual viewer's ratio dial shouldn't touch the
shared backend state either).
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence

from backend.app.order_flow.footprint_candle import FootprintCandle
from backend.app.order_flow.models import FootprintNode

DEFAULT_IMBALANCE_RATIO_PCT = 400.0
VALID_IMBALANCE_RATIOS_PCT = (200.0, 300.0, 400.0, 500.0)


@dataclass
class DominanceResult:
    confirmed: bool
    direction: str  # "BUYER_DOMINANCE" | "SELLER_DOMINANCE" | "NONE"
    opposing_aggression: bool
    imbalance_confirmed: bool
    microstructure_break: bool
    components: Dict[str, float] = field(default_factory=dict)


def _has_ask_side_imbalance(footprint: Dict[float, FootprintNode], ratio_pct: float) -> bool:
    """Aggressive buying at a higher price level dwarfs resting sell
    interest one tick below — same comparison as
    order_flow.analysis.check_diagonal_imbalance's buy-imbalance check.
    """
    ratio = ratio_pct / 100.0
    sorted_prices = sorted(footprint.keys())
    for i in range(len(sorted_prices) - 1):
        lower = footprint[sorted_prices[i]]
        higher = footprint[sorted_prices[i + 1]]
        if lower.bid_volume > 0 and higher.ask_volume >= ratio * lower.bid_volume:
            return True
    return False


def _has_bid_side_imbalance(footprint: Dict[float, FootprintNode], ratio_pct: float) -> bool:
    """Mirror: aggressive selling at a higher level dwarfs resting ask
    interest one tick below — order_flow.analysis's sell-imbalance check.
    """
    ratio = ratio_pct / 100.0
    sorted_prices = sorted(footprint.keys())
    for i in range(len(sorted_prices) - 1):
        lower = footprint[sorted_prices[i]]
        higher = footprint[sorted_prices[i + 1]]
        if lower.ask_volume > 0 and higher.bid_volume >= ratio * lower.ask_volume:
            return True
    return False


def _microstructure_break(
    absorption_candles: Sequence[FootprintCandle],
    confirmation_candles: Sequence[FootprintCandle],
    direction: str,  # "BULLISH" | "BEARISH"
) -> bool:
    if not absorption_candles or not confirmation_candles:
        return False
    if direction == "BULLISH":
        micro_swing_high = max(c.high for c in absorption_candles)
        return any(c.high > micro_swing_high for c in confirmation_candles)
    micro_swing_low = min(c.low for c in absorption_candles)
    return any(c.low < micro_swing_low for c in confirmation_candles)


def evaluate_bullish_dominance(
    absorption_candles: Sequence[FootprintCandle],
    confirmation_candles: Sequence[FootprintCandle],
    imbalance_ratio_pct: float = DEFAULT_IMBALANCE_RATIO_PCT,
) -> DominanceResult:
    """Bullish confirmation requires, in order: seller aggression already
    absorbed (caller's job — this evaluates what comes AFTER), buyer
    aggression appearing, ask-side imbalance at the configured ratio, and
    a bullish microstructure break.
    """
    none_result = DominanceResult(
        confirmed=False, direction="NONE", opposing_aggression=False,
        imbalance_confirmed=False, microstructure_break=False,
    )
    if not confirmation_candles:
        return none_result

    opposing_delta = sum(c.delta for c in confirmation_candles)
    opposing_aggression = opposing_delta > 0

    imbalance_confirmed = any(_has_ask_side_imbalance(c.footprint, imbalance_ratio_pct) for c in confirmation_candles)
    micro_break = _microstructure_break(absorption_candles, confirmation_candles, "BULLISH")

    confirmed = opposing_aggression and imbalance_confirmed and micro_break

    return DominanceResult(
        confirmed=confirmed,
        direction="BUYER_DOMINANCE" if confirmed else "NONE",
        opposing_aggression=opposing_aggression,
        imbalance_confirmed=imbalance_confirmed,
        microstructure_break=micro_break,
        components={"opposing_delta": float(opposing_delta), "imbalance_ratio_pct": imbalance_ratio_pct},
    )


def evaluate_bearish_dominance(
    absorption_candles: Sequence[FootprintCandle],
    confirmation_candles: Sequence[FootprintCandle],
    imbalance_ratio_pct: float = DEFAULT_IMBALANCE_RATIO_PCT,
) -> DominanceResult:
    none_result = DominanceResult(
        confirmed=False, direction="NONE", opposing_aggression=False,
        imbalance_confirmed=False, microstructure_break=False,
    )
    if not confirmation_candles:
        return none_result

    opposing_delta = sum(c.delta for c in confirmation_candles)
    opposing_aggression = opposing_delta < 0

    imbalance_confirmed = any(_has_bid_side_imbalance(c.footprint, imbalance_ratio_pct) for c in confirmation_candles)
    micro_break = _microstructure_break(absorption_candles, confirmation_candles, "BEARISH")

    confirmed = opposing_aggression and imbalance_confirmed and micro_break

    return DominanceResult(
        confirmed=confirmed,
        direction="SELLER_DOMINANCE" if confirmed else "NONE",
        opposing_aggression=opposing_aggression,
        imbalance_confirmed=imbalance_confirmed,
        microstructure_break=micro_break,
        components={"opposing_delta": float(opposing_delta), "imbalance_ratio_pct": imbalance_ratio_pct},
    )
