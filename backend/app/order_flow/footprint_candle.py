"""Timeframe-bucketed OHLC + footprint candles for the Order Flow
Footprint Chart module.

OrderFlowEngine/OrderFlowState (engine.py/models.py) track one
continuously-accumulating footprint per instrument with no candle
boundaries — good for a live "current state" panel, not for a footprint
chart that needs discrete Open/High/Low/Close candles with their own
footprint each. This module adds that missing bucketing layer, reusing
the existing pure classification/imbalance functions (analysis.py) and
the existing FootprintNode model rather than duplicating either.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .analysis import check_diagonal_imbalance, check_stacked_imbalance
from .models import FootprintNode

TIMEFRAME_SECONDS: Dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
}


def floor_to_timeframe(ts: datetime, timeframe: str) -> datetime:
    seconds = TIMEFRAME_SECONDS.get(timeframe, 300)
    epoch = ts.timestamp()
    floored = epoch - (epoch % seconds)
    return datetime.fromtimestamp(floored, tz=ts.tzinfo)


class FootprintCandle(BaseModel):
    instrument_key: str
    timeframe: str
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    is_closed: bool = False
    footprint: Dict[float, FootprintNode] = Field(default_factory=dict)
    buy_volume: int = 0
    sell_volume: int = 0
    delta: int = 0
    poc_price: Optional[float] = None  # price level with the most total volume this candle


class FootprintCandleAggregator:
    """Per (instrument, timeframe) rolling candle builder. Keeps only the
    current candle plus a short bounded history in memory — no
    persistence layer, matching every other in-memory state holder in
    this codebase (algo_config_state, manual_trading_engine.positions).
    """

    def __init__(self, imbalance_ratio_pct: float = 300.0, stacked_min_consecutive: int = 3, max_history: int = 200):
        self.imbalance_ratio_pct = imbalance_ratio_pct
        self.stacked_min_consecutive = stacked_min_consecutive
        self.max_history = max_history
        self._current: Dict[str, Dict[str, FootprintCandle]] = {}
        self._history: Dict[str, Dict[str, List[FootprintCandle]]] = {}

    def set_imbalance_ratio_pct(self, ratio_pct: float) -> None:
        self.imbalance_ratio_pct = ratio_pct

    def get_current(self, instrument_key: str, timeframe: str) -> Optional[FootprintCandle]:
        return self._current.get(instrument_key, {}).get(timeframe)

    def get_history(self, instrument_key: str, timeframe: str) -> List[FootprintCandle]:
        return list(self._history.get(instrument_key, {}).get(timeframe, []))

    def process_tick(
        self, instrument_key: str, price: float, volume: int, direction: str, timestamp: datetime, timeframe: str,
    ) -> FootprintCandle:
        """direction is "AGGRESSIVE_BUY" or "AGGRESSIVE_SELL" — already
        classified by the caller (the mock feed's own bid/ask flag today;
        order_flow.analysis.classify_trade_direction for a real feed with
        actual depth, once one exists).
        """
        bucket_start = floor_to_timeframe(timestamp, timeframe)

        by_tf = self._current.setdefault(instrument_key, {})
        candle = by_tf.get(timeframe)

        if candle is None or candle.open_time != bucket_start:
            if candle is not None:
                self._close_candle(instrument_key, timeframe, candle)
            candle = FootprintCandle(
                instrument_key=instrument_key, timeframe=timeframe, open_time=bucket_start,
                open=price, high=price, low=price, close=price,
            )
            by_tf[timeframe] = candle

        candle.high = max(candle.high, price)
        candle.low = min(candle.low, price)
        candle.close = price

        node = candle.footprint.get(price)
        if node is None:
            node = FootprintNode(price=price)
            candle.footprint[price] = node

        if direction == "AGGRESSIVE_BUY":
            node.ask_volume += volume
            candle.buy_volume += volume
        elif direction == "AGGRESSIVE_SELL":
            node.bid_volume += volume
            candle.sell_volume += volume
        node.total_volume = node.bid_volume + node.ask_volume
        node.delta = node.ask_volume - node.bid_volume

        candle.delta = candle.buy_volume - candle.sell_volume
        candle.poc_price = max(candle.footprint.values(), key=lambda n: n.total_volume).price if candle.footprint else None

        # Recomputed on every tick — footprints are small (tens of price
        # levels per candle), and this is the only way stacked-imbalance
        # zones stay correct as new levels fill in mid-candle.
        for n in candle.footprint.values():
            n.buy_imbalance = False
            n.sell_imbalance = False
        check_diagonal_imbalance(candle.footprint, ratio=self.imbalance_ratio_pct / 100.0)
        check_stacked_imbalance(candle.footprint, min_consecutive=self.stacked_min_consecutive)

        return candle

    def _close_candle(self, instrument_key: str, timeframe: str, candle: FootprintCandle) -> None:
        candle.is_closed = True
        history = self._history.setdefault(instrument_key, {}).setdefault(timeframe, [])
        history.append(candle)
        if len(history) > self.max_history:
            history.pop(0)
