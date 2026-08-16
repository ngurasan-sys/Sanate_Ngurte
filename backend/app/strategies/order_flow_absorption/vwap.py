"""Session VWAP for OFAO's underlying instruments.

The existing VWAP implementation (market_data/processor.py's
CandleAggregator) is tied to MARKET_TICK, which only ever carries index
*spot* ticks from the live Upstox `ltpc` feed (upstox_v3.py) — it has
never seen a "NIFTY FUT"/"SENSEX FUT" instrument key and never will
under the current wiring. Rather than bolt OFAO onto a pipeline that
structurally doesn't cover its instruments, this mirrors that exact
formula (cumulative price*volume / cumulative volume) against the data
OFAO actually has: its own FootprintCandle history, price-weighted by
each level's total_volume.
"""

from typing import List, Optional

from backend.app.order_flow.footprint_candle import FootprintCandle


def compute_session_vwap(candles: List[FootprintCandle]) -> Optional[float]:
    cumulative_pv = 0.0
    cumulative_volume = 0.0
    for candle in candles:
        for price, node in candle.footprint.items():
            cumulative_pv += price * node.total_volume
            cumulative_volume += node.total_volume
    if cumulative_volume <= 0:
        return None
    return cumulative_pv / cumulative_volume
