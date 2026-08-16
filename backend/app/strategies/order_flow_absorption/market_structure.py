"""Higher-timeframe market structure classification — the Context Engine
(spec §1). No structure classifier existed anywhere in this codebase
before this module (the closest thing, trending_oi_price_action/engine.py,
has only a "simplistic swing high detection" comment for one specific
purpose, not a general HH/HL/LH/LL classifier).

Swing points are detected with a strict fractal rule (a bar's high/low
must exceed every bar within `lookback` positions on *both* sides) —
which means the most recent `lookback` bars can never be classified as a
confirmed swing yet, by construction. That's deliberate: a swing isn't
real until bars on both sides confirm it, so this never uses information
that wasn't actually available at the time.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence


class StructureBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    BALANCED = "BALANCED"
    UNKNOWN = "UNKNOWN"


class SwingType(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


@dataclass(frozen=True)
class SwingPoint:
    index: int
    price: float
    type: SwingType


@dataclass
class StructureBar:
    """Minimal OHLC shape this module needs — deliberately not coupled to
    the market_data.Candle model, so it can be fed resampled 1H/4H bars
    built from 15m Candles without a conversion layer here.
    """
    high: float
    low: float
    close: float


def find_swing_points(bars: Sequence[StructureBar], lookback: int = 2) -> List[SwingPoint]:
    swings: List[SwingPoint] = []
    n = len(bars)
    for i in range(lookback, n - lookback):
        neighbors = bars[i - lookback: i] + bars[i + 1: i + lookback + 1]
        if all(bars[i].high > b.high for b in neighbors):
            swings.append(SwingPoint(index=i, price=bars[i].high, type=SwingType.HIGH))
        if all(bars[i].low < b.low for b in neighbors):
            swings.append(SwingPoint(index=i, price=bars[i].low, type=SwingType.LOW))
    return swings


def classify_structure(bars: Sequence[StructureBar], lookback: int = 2) -> StructureBias:
    """BULLISH: the last two confirmed swing highs are ascending AND the
    last two confirmed swing lows are ascending (higher highs + higher
    lows). BEARISH: the mirror image. UNKNOWN when there aren't enough
    confirmed swings yet to say anything. BALANCED: enough swings exist,
    but neither the bullish nor bearish pattern holds (mixed signals —
    e.g. a higher high paired with a lower low, or a flat/overlapping
    range) — this is a real classification, not a fallback for missing
    data.
    """
    swings = find_swing_points(bars, lookback)
    highs = [s for s in swings if s.type == SwingType.HIGH]
    lows = [s for s in swings if s.type == SwingType.LOW]

    if len(highs) < 2 or len(lows) < 2:
        return StructureBias.UNKNOWN

    higher_highs = highs[-1].price > highs[-2].price
    higher_lows = lows[-1].price > lows[-2].price
    lower_highs = highs[-1].price < highs[-2].price
    lower_lows = lows[-1].price < lows[-2].price

    if higher_highs and higher_lows:
        return StructureBias.BULLISH
    if lower_highs and lower_lows:
        return StructureBias.BEARISH
    return StructureBias.BALANCED


def is_holding_above(bars: Sequence[StructureBar], reference_price: float, min_closes: int = 3) -> bool:
    """"Bullish acceptance" — the last `min_closes` bars all closed above
    a reference level (POC/VWAP/prior value). Requires at least
    min_closes bars; returns False (not "unknown") when there isn't
    enough history, since "holding above" is a claim about recent bars
    specifically, not something that can default to true.
    """
    if len(bars) < min_closes:
        return False
    return all(b.close > reference_price for b in bars[-min_closes:])


def is_holding_below(bars: Sequence[StructureBar], reference_price: float, min_closes: int = 3) -> bool:
    if len(bars) < min_closes:
        return False
    return all(b.close < reference_price for b in bars[-min_closes:])


def resample_bars(source_bars: Sequence[StructureBar], group_size: int) -> List[StructureBar]:
    """Rolls up `group_size` consecutive smaller bars into one larger
    bar (e.g. four 15m bars -> one 1H bar). Pure OHLC aggregation, no
    volume — this module only needs high/low/close for structure. A
    trailing partial group (fewer than group_size bars left) is dropped
    rather than emitted as a short bar, since an incomplete higher-
    timeframe bar isn't a real bar yet.
    """
    resampled: List[StructureBar] = []
    for start in range(0, len(source_bars) - group_size + 1, group_size):
        group = source_bars[start:start + group_size]
        resampled.append(StructureBar(
            high=max(b.high for b in group),
            low=min(b.low for b in group),
            close=group[-1].close,
        ))
    return resampled
