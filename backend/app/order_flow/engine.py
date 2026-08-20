from typing import Dict, Optional, Any, Tuple
from .models import OrderFlowState, FootprintNode, DepthLevel
from .analysis import (
    calculate_trade_size,
    classify_trade_direction,
    calculate_classification_confidence,
    calculate_spread_and_mid,
    calculate_all_depth_imbalances
)


class OrderFlowEngine:
    def __init__(self, depth_limit: int = 30):
        # Pydantic state objects exposed by the engine (API contract)
        self.states: Dict[str, OrderFlowState] = {}
        # raw_state stores lightweight metadata and caches to avoid repeated work
        self.raw_state: Dict[str, Dict[str, Any]] = {}
        # maximum depth we keep / construct
        self.depth_limit = depth_limit

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
                "last_classification": "UNKNOWN",
                # caching fingerprint of last processed depth to avoid Pydantic re-construction
                "depth_fingerprint": ((), ()),  # (bids_fp, asks_fp)
            }

    def _depth_fingerprint(self, depth_section: list) -> Tuple[Tuple, ...]:
        """Create a small, hashable fingerprint for a depth list of dicts.
        Each element is (price, quantity, orders) truncated to depth_limit.
        """
        fp = []
        limit = self.depth_limit
        for i, d in enumerate(depth_section):
            if i >= limit:
                break
            # make sure we use primitive types only
            price = d.get("price")
            qty = d.get("quantity")
            orders = d.get("orders")
            fp.append((price, qty, orders))
        return tuple(fp)

    def process_tick(self, tick: dict) -> Optional[OrderFlowState]:
        """Process a single tick. Optimized hot path with caching to avoid
        unnecessary Pydantic construction and repeated computations.

        Returns the OrderFlowState for the instrument (preserves API contract).
        """
        instrument_key = tick.get("instrument_key")
        if not instrument_key:
            return None

        self._init_raw_state(instrument_key)
        raw = self.raw_state[instrument_key]

        timestamp = tick.get("ltt", tick.get("exchange_timestamp", 0))

        # lazily create Pydantic state object only when first needed
        if instrument_key not in self.states:
            self.states[instrument_key] = OrderFlowState(
                instrument_key=instrument_key,
                timestamp=timestamp
            )

        state = self.states[instrument_key]
        state.timestamp = timestamp

        # --- Update Greeks (cheap: only assign provided keys) ---
        greeks_data = tick.get("greeks")
        if greeks_data:
            if state.greeks is None:
                state.greeks = type(state).Config.model_construct_fields.get("greeks", None) if False else state.greeks
                # Fallback: simple assignment to Pydantic Greeks object if present
                try:
                    from .models import Greeks
                    if state.greeks is None:
                        state.greeks = Greeks()
                except Exception:
                    state.greeks = None
            if state.greeks is not None:
                for k, v in greeks_data.items():
                    if v is not None:
                        setattr(state.greeks, k, v)

        # --- Update Depth if present, but avoid rebuilding unchanged depths ---
        depth = tick.get("market_depth")
        if depth:
            bids = depth.get("bids", [])
            asks = depth.get("asks", [])

            bids_fp = self._depth_fingerprint(bids)
            asks_fp = self._depth_fingerprint(asks)
            last_bids_fp, last_asks_fp = raw.get("depth_fingerprint", ((), ()))

            # Only rebuild Pydantic DepthLevel lists when fingerprint differs
            if bids_fp != last_bids_fp:
                # build up to depth_limit
                limited_bids = bids[: self.depth_limit]
                # reuse existing DepthLevel objects where possible based on price match
                state.depth.bids = [
                    DepthLevel.model_construct(
                        price=b["price"],
                        quantity=b["quantity"],
                        orders=b.get("orders", 0)
                    ) if isinstance(b, dict) else b
                    for b in limited_bids
                ]
                if state.depth.bids:
                    raw["best_bid"] = state.depth.bids[0].price
            # if same, leave state.depth.bids unchanged

            if asks_fp != last_asks_fp:
                limited_asks = asks[: self.depth_limit]
                state.depth.asks = [
                    DepthLevel.model_construct(
                        price=a["price"],
                        quantity=a["quantity"],
                        orders=a.get("orders", 0)
                    ) if isinstance(a, dict) else a
                    for a in limited_asks
                ]
                if state.depth.asks:
                    raw["best_ask"] = state.depth.asks[0].price

            # store new fingerprints
            raw["depth_fingerprint"] = (bids_fp, asks_fp)

            # Always update spread/mid using the (possibly) updated bests
            state.spread, state.mid_price = calculate_spread_and_mid(raw.get("best_bid"), raw.get("best_ask"))

            # Define requested imbalance depths
            imbalance_depths = (1, 3, 5, 10, 20, 30)

            # Calculate all requested imbalances in a single O(N) pass
            imbalances = calculate_all_depth_imbalances(
                state.depth.bids, state.depth.asks, imbalance_depths
            )

            # Update state with calculated imbalances, setting missing ones to None
            for n in imbalance_depths:
                attr = f"depth_imbalance_{n}"
                if n in imbalances:
                    setattr(state, attr, imbalances[n])
                elif getattr(state, attr, None) is not None:
                    setattr(state, attr, None)

        # --- Process trade flow ---
        ltp = tick.get("ltp")
        ltq = tick.get("ltq")
        cumulative_volume = tick.get("volume")

        if cumulative_volume is not None:
            raw["previous_cumulative_volume"] = raw.get("current_cumulative_volume")
            raw["current_cumulative_volume"] = cumulative_volume

        if ltp is not None:
            # 1. Reconcile Trade Size
            trade_size, source, quality = calculate_trade_size(
                ltq,
                raw.get("current_cumulative_volume"),
                raw.get("previous_cumulative_volume")
            )

            state.trade_size = trade_size
            state.trade_size_source = source
            state.volume_quality = quality

            if trade_size > 0:
                # 2. Classify Direction
                direction = classify_trade_direction(
                    ltp,
                    raw.get("best_ask"),
                    raw.get("best_bid"),
                    raw.get("previous_trade_price")
                )

                if direction == "UNKNOWN" and raw.get("last_classification") != "UNKNOWN":
                    direction = raw.get("last_classification")

                raw["last_classification"] = direction
                state.classification_mode = direction

                # 3. Update Executed Flow
                if direction == "AGGRESSIVE_BUY":
                    state.buy_volume += trade_size
                    if ltp not in state.footprint:
                        state.footprint[ltp] = FootprintNode.model_construct(
                            price=ltp,
                            bid_volume=0,
                            ask_volume=0,
                            delta=0,
                            total_volume=0,
                            buy_imbalance=False,
                            sell_imbalance=False
                        )
                    state.footprint[ltp].ask_volume += trade_size
                elif direction == "AGGRESSIVE_SELL":
                    state.sell_volume += trade_size
                    if ltp not in state.footprint:
                        state.footprint[ltp] = FootprintNode.model_construct(
                            price=ltp,
                            bid_volume=0,
                            ask_volume=0,
                            delta=0,
                            total_volume=0,
                            buy_imbalance=False,
                            sell_imbalance=False
                        )
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
