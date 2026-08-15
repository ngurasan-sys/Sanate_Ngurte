"""Pure, stateless logic for the Expiry Day Reversal strategy.

Kept separate from engine.py so every decision rule can be unit tested
without constructing the stateful engine or touching the event bus.
"""

from datetime import time
from typing import Optional, Tuple


def is_weak_bullish_move(
    futures_classification: str,
    candle_body: float,
    daily_atr: float,
    body_atr_ratio_threshold: float,
) -> bool:
    """A. A bullish move is "weak" when it's driven by shorts exiting
    (SHORT_COVERING) rather than fresh buying (LONG_BUILDUP), AND the
    candles themselves are small relative to the day's average range.
    """
    driven_by_short_covering = futures_classification == "SHORT_COVERING"
    if daily_atr <= 0:
        weak_candles = False
    else:
        weak_candles = (abs(candle_body) / daily_atr) < body_atr_ratio_threshold
    return driven_by_short_covering and weak_candles


def is_weak_bearish_move(
    futures_classification: str,
    candle_body: float,
    daily_atr: float,
    body_atr_ratio_threshold: float,
) -> bool:
    """Symmetric bearish case: a down-move driven by LONG_UNWINDING
    (longs exiting) rather than fresh SHORT_BUILDUP, with small candles.
    """
    driven_by_long_unwinding = futures_classification == "LONG_UNWINDING"
    if daily_atr <= 0:
        weak_candles = False
    else:
        weak_candles = (abs(candle_body) / daily_atr) < body_atr_ratio_threshold
    return driven_by_long_unwinding and weak_candles


def detect_oi_shift(
    ce_oi_now: float,
    ce_oi_before: float,
    pe_oi_now: float,
    pe_oi_before: float,
    call_oi_increase_threshold: float,
    put_oi_decrease_threshold: float,
) -> Tuple[bool, bool]:
    """B. Returns (bearish_shift, bullish_shift).

    Bearish shift: call OI rises sharply (fresh resistance being built)
    while put OI drops sharply (put sellers exiting, support removed) —
    the "call sellers entering, put sellers exiting" signature.

    Bullish shift is the mirror image: put OI rises while call OI drops.
    """
    call_increase = ce_oi_now - ce_oi_before
    put_decrease = pe_oi_before - pe_oi_now
    put_increase = pe_oi_now - pe_oi_before
    call_decrease = ce_oi_before - ce_oi_now

    bearish_shift = (
        call_increase >= call_oi_increase_threshold
        and put_decrease >= put_oi_decrease_threshold
    )
    bullish_shift = (
        put_increase >= call_oi_increase_threshold
        and call_decrease >= put_oi_decrease_threshold
    )
    return bearish_shift, bullish_shift


def is_structural_break(
    closes: list,
    opens: list,
    day_low: float,
    day_high: float,
    direction: str,
    min_candles: int,
) -> bool:
    """B. A sharp move breaking the day's low/high on `min_candles`
    consecutive large-bodied candles in the same direction.
    """
    if len(closes) < min_candles or len(opens) < min_candles:
        return False

    recent_closes = closes[-min_candles:]
    recent_opens = opens[-min_candles:]

    if direction == "BEARISH":
        all_red = all(c < o for c, o in zip(recent_closes, recent_opens))
        broke_low = recent_closes[-1] < day_low
        return all_red and broke_low
    elif direction == "BULLISH":
        all_green = all(c > o for c, o in zip(recent_closes, recent_opens))
        broke_high = recent_closes[-1] > day_high
        return all_green and broke_high
    return False


def should_skip_late_session_trade(
    is_expiry_day: bool,
    current_time: time,
    late_session_start: time,
    intraday_range: float,
    daily_atr: float,
    atr_exhaustion_ratio: float,
) -> Tuple[bool, str]:
    """E. Even with strong OI confirmation, skip new entries late in an
    expiry-day session once the day's range has already used up most of
    the average daily range — premium erosion risk outweighs the
    remaining reward.
    """
    if not is_expiry_day:
        return False, ""
    if current_time < late_session_start:
        return False, ""
    if daily_atr <= 0:
        return False, ""

    atr_usage = intraday_range / daily_atr
    if atr_usage >= atr_exhaustion_ratio:
        return True, (
            f"Expiry day, late session (after {late_session_start.strftime('%H:%M')}): "
            f"range has used {atr_usage:.0%} of average daily range — "
            f"risk/reward unfavorable despite OI confirmation"
        )
    return False, ""


def compute_tier_prices(
    breakout_price: float,
    direction: str,
    tier_2_offset_points: float,
    tier_3_offset_points: float,
) -> Tuple[float, float, float]:
    """C. Laddered entry levels: tier 1 at the breakout, tier 2 slightly
    further in the direction of the move, tier 3 near the prior
    support-turned-resistance (or resistance-turned-support) zone.
    """
    if direction == "BEARISH":
        tier_1 = breakout_price
        tier_2 = breakout_price - tier_2_offset_points
        tier_3 = breakout_price - tier_3_offset_points
    else:
        tier_1 = breakout_price
        tier_2 = breakout_price + tier_2_offset_points
        tier_3 = breakout_price + tier_3_offset_points
    return tier_1, tier_2, tier_3


def compute_breakout_stop_loss(
    breakout_candle_high: float,
    breakout_candle_low: float,
    direction: str,
    buffer_points: float,
) -> float:
    """C. Stop-loss placed just beyond the breakout candle's extreme —
    if price reclaims that level, the breakout has failed.
    """
    if direction == "BEARISH":
        return breakout_candle_high + buffer_points
    return breakout_candle_low - buffer_points


def compute_partial_exit_lots(lots_held: int, partial_exit_pct: float) -> int:
    """D. Booked once price moves favorably after tier 1 fills, before
    waiting for tiers 2/3. Always exits at least 1 lot if any are held.
    """
    if lots_held <= 0:
        return 0
    return max(1, int(lots_held * (partial_exit_pct / 100.0)))


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))
