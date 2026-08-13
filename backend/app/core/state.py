from typing import Dict, Any, List
from collections import deque

class MarketState:
    """
    In-memory state layer for the hot path.
    Avoids DuckDB queries for real-time processing.
    Maintains rolling state like latest ticks, option chain, and indicators.
    """
    def __init__(self):
        self.latest_ticks: Dict[str, Any] = {}
        self.tick_history: Dict[str, deque] = {}
        self.candles: Dict[str, List[Any]] = {}
        self.option_chain: Dict[str, Any] = {}
        self.oi_data: Dict[str, Any] = {}
        self.greeks: Dict[str, Any] = {}
        self.indicators: Dict[str, Any] = {}
        self.max_history_ticks = 100

    def update_tick(self, instrument: str, tick_data: Any):
        self.latest_ticks[instrument] = tick_data
        if instrument not in self.tick_history:
            self.tick_history[instrument] = deque(maxlen=self.max_history_ticks)
        self.tick_history[instrument].append(tick_data)

    def get_latest_tick(self, instrument: str) -> Any:
        return self.latest_ticks.get(instrument)

    def update_option_chain(self, instrument: str, option_data: Any):
        self.option_chain[instrument] = option_data

# Global market state instance
market_state = MarketState()
