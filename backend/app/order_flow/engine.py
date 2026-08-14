from typing import Dict, Optional, Any
from .models import OrderFlowState, FootprintNode, DepthLevel, DepthData, Greeks
from .analysis import (
    calculate_trade_size,
    classify_trade_direction,
    calculate_classification_confidence,
    calculate_spread_and_mid,
    calculate_depth_imbalance
)

class OrderFlowEngine:
    def __init__(self):
        self.states: Dict[str, OrderFlowState] = {}
        self.raw_state: Dict[str, Dict[str, Any]] = {}

    def get_state(self, instrument_key: str) -> Optional[OrderFlowState]:
        return self.states.get(instrument_key)

    def _init_raw_state(self, instrument_key: str):
        if instrument_key not in self.raw_state:
            self.raw_state[instrument_key] = {
                "previous_trade_price": None,
                "previous_cumulative_volume": None,
                "current_cumulative_volume": None,
                "best_bid": None,
                "best_ask": None,
                "last_classification": "UNKNOWN"
            }

    def process_tick(self, tick: dict) -> Optional[OrderFlowState]:
        instrument_key = tick.get("instrument_key")
        if not instrument_key:
            return None

        self._init_raw_state(instrument_key)
        raw = self.raw_state[instrument_key]

        timestamp = tick.get("ltt", tick.get("exchange_timestamp", 0))

        if instrument_key not in self.states:
            self.states[instrument_key] = OrderFlowState(
                instrument_key=instrument_key,
                timestamp=timestamp
            )

        state = self.states[instrument_key]
        state.timestamp = timestamp

        # Update Greeks if present
        greeks_data = tick.get("greeks")
        if greeks_data:
            if state.greeks is None:
                state.greeks = Greeks()
            for k, v in greeks_data.items():
                if v is not None:
                    setattr(state.greeks, k, v)

        # Update Depth if present
        depth = tick.get("market_depth")
        if depth:
            if "bids" in depth:
                state.depth.bids = [DepthLevel(**b) for b in depth["bids"][:30]]
                if state.depth.bids:
                    raw["best_bid"] = state.depth.bids[0].price
            if "asks" in depth:
                state.depth.asks = [DepthLevel(**a) for a in depth["asks"][:30]]
                if state.depth.asks:
                    raw["best_ask"] = state.depth.asks[0].price

            state.spread, state.mid_price = calculate_spread_and_mid(raw["best_bid"], raw["best_ask"])

            # Update imbalances
            state.depth_imbalance_1 = calculate_depth_imbalance(state.depth.bids, state.depth.asks, 1)
            state.depth_imbalance_3 = calculate_depth_imbalance(state.depth.bids, state.depth.asks, 3)
            state.depth_imbalance_5 = calculate_depth_imbalance(state.depth.bids, state.depth.asks, 5)
            state.depth_imbalance_10 = calculate_depth_imbalance(state.depth.bids, state.depth.asks, 10)
            state.depth_imbalance_20 = calculate_depth_imbalance(state.depth.bids, state.depth.asks, 20)
            state.depth_imbalance_30 = calculate_depth_imbalance(state.depth.bids, state.depth.asks, 30)

        # Process trade flow
        ltp = tick.get("ltp")
        ltq = tick.get("ltq")
        cumulative_volume = tick.get("volume")

        if cumulative_volume is not None:
            raw["previous_cumulative_volume"] = raw["current_cumulative_volume"]
            raw["current_cumulative_volume"] = cumulative_volume

        if ltp is not None:
            # 1. Reconcile Trade Size
            trade_size, source, quality = calculate_trade_size(
                ltq,
                raw["current_cumulative_volume"],
                raw["previous_cumulative_volume"]
            )

            state.trade_size = trade_size
            state.trade_size_source = source
            state.volume_quality = quality

            if trade_size > 0:
                # 2. Classify Direction
                direction = classify_trade_direction(
                    ltp,
                    raw["best_ask"],
                    raw["best_bid"],
                    raw["previous_trade_price"]
                )

                if direction == "UNKNOWN" and raw["last_classification"] != "UNKNOWN":
                    direction = raw["last_classification"]

                raw["last_classification"] = direction
                state.classification_mode = direction

                # 3. Update Executed Flow
                if direction == "AGGRESSIVE_BUY":
                    state.buy_volume += trade_size
                    if ltp not in state.footprint:
                        state.footprint[ltp] = FootprintNode(price=ltp)
                    state.footprint[ltp].ask_volume += trade_size
                elif direction == "AGGRESSIVE_SELL":
                    state.sell_volume += trade_size
                    if ltp not in state.footprint:
                        state.footprint[ltp] = FootprintNode(price=ltp)
                    state.footprint[ltp].bid_volume += trade_size
                else:
                    state.unknown_volume += trade_size

                state.bar_delta = state.buy_volume - state.sell_volume
                state.cvd = state.bar_delta

                state.classification_confidence = calculate_classification_confidence(
                    state.buy_volume, state.sell_volume, state.unknown_volume
                )

                if ltp in state.footprint:
                    fp = state.footprint[ltp]
                    fp.total_volume = fp.bid_volume + fp.ask_volume
                    fp.delta = fp.ask_volume - fp.bid_volume

            raw["previous_trade_price"] = ltp

        return state
