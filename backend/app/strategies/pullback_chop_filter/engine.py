import asyncio
import logging
from datetime import datetime, time
from typing import Dict, Any, Optional

from backend.app.core.event_bus import event_bus
from backend.app.market_data.models import Tick, Candle
from backend.app.strategies.trending_oi_price_action.indicators import SuperTrendIndicator

logger = logging.getLogger(__name__)

class PullbackChopFilterStrategy:
    def __init__(self, strategy_id: str = "pullback_chop_filter"):
        self.strategy_id = strategy_id
        self.running = False
        self.supertrend_period = 10
        self.supertrend_multiplier = 2.0

        # Position trackers per instrument
        self.positions = {}

    def _get_instrument_state(self, instrument: str) -> Dict[str, Any]:
        if instrument not in self.positions:
            self.positions[instrument] = {
                "market_state": "CHOP_ZONE",  # CHOP_ZONE, TRENDING_BULLISH, TRENDING_BEARISH
                "internal_state": "WAITING", # WAITING, BULLISH_TREND_CONFIRMED, BULLISH_TIER_1, BULLISH_TIER_2, BEARISH_TREND_CONFIRMED, BEARISH_TIER_1, BEARISH_TIER_2, INVALIDATED
                "supertrend": SuperTrendIndicator(period=self.supertrend_period, multiplier=self.supertrend_multiplier),
                "last_vwap": None,
                "current_st": None,
                "upper_band": None,
                "lower_band": None,
                "oi_diff_pct": 0.0,
                "last_ltp": None,
                "active_signal": {
                    "type": "WAIT",
                    "message": "Initializing...",
                    "color": "slate"
                }
            }
        return self.positions[instrument]

    def start(self):
        if self.running:
            return
        self.running = True

        event_bus.subscribe("CANDLE_CLOSED", self._handle_candle_closed)
        event_bus.subscribe("MARKET_TICK", self._handle_market_tick)
        event_bus.subscribe("trending_oi", self._handle_trending_oi)

        logger.info(f"Pullback Chop Filter Strategy ({self.strategy_id}) started")

    def stop(self):
        self.running = False

    async def _emit_state(self, instrument: str, state: Dict[str, Any]):
        payload = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "symbol": instrument,
            "price_data": {
                "ltp": state["last_ltp"] or 0.0,
                "vwap": state["last_vwap"] or 0.0,
                "supertrend": state["current_st"] or 0.0,
                "upper_band": state["upper_band"] or 0.0,
                "lower_band": state["lower_band"] or 0.0
            },
            "oi_data": {
                "diff_pct": state["oi_diff_pct"]
            },
            "market_state": state["market_state"],
            "internal_state": state["internal_state"],
            "active_signal": state["active_signal"]
        }
        await event_bus.publish("pullback_chop_filter_state", payload)

    async def _handle_candle_closed(self, candle: Candle):
        if candle.timeframe != "3m" and candle.timeframe != "1d":
            return

        if "FUT" not in candle.instrument and "NIFTY" not in candle.instrument:
            return

        state = self._get_instrument_state(candle.instrument)

        # We only use 3m for VWAP and ST updates and SL logic
        if candle.timeframe == "3m":
            st_result = state["supertrend"].add_candle(candle.high, candle.low, candle.close)
            if st_result:
                state["current_st"] = st_result["supertrend"]

            if candle.vwap is not None:
                state["last_vwap"] = candle.vwap

            # Evaluate bands
            if state["last_vwap"] is not None and state["current_st"] is not None:
                state["upper_band"] = max(state["last_vwap"], state["current_st"])
                state["lower_band"] = min(state["last_vwap"], state["current_st"])

            # Check invalidation logic based on 3m candle CLOSE
            await self._check_invalidation(candle, state)

            # Run state evaluation
            await self._evaluate_state(candle.instrument, state, candle.close)

    async def _handle_market_tick(self, tick: Tick):
        if "FUT" not in tick.instrument and "NIFTY" not in tick.instrument:
            return

        state = self._get_instrument_state(tick.instrument)
        state["last_ltp"] = tick.price

        await self._evaluate_state(tick.instrument, state, tick.price)

    async def _handle_trending_oi(self, data: Dict[str, Any]):
        if data.get("view") != "spot_trending_oi":
            return

        row = data.get("row", {})
        underlying = data.get("underlying", "NIFTY")
        instrument = f"{underlying} FUT" # Ensure matching keys

        state = self._get_instrument_state(instrument)
        state["oi_diff_pct"] = row.get("directionPercent", 0.0)

        if state["last_ltp"] is not None:
            await self._evaluate_state(instrument, state, state["last_ltp"])

    async def _check_invalidation(self, candle: Candle, state: Dict[str, Any]):
        if state["last_vwap"] is None:
            return

        if state["internal_state"] in ["BULLISH_TREND_CONFIRMED", "BULLISH_TIER_1", "BULLISH_TIER_2"]:
            if candle.close < state["last_vwap"]:
                state["internal_state"] = "INVALIDATED"
                state["market_state"] = "CHOP_ZONE"
                state["active_signal"] = {
                    "type": "STOP_LOSS_HIT",
                    "message": "Candle closed below VWAP. Thesis invalidated.",
                    "color": "rose"
                }
        elif state["internal_state"] in ["BEARISH_TREND_CONFIRMED", "BEARISH_TIER_1", "BEARISH_TIER_2"]:
            if candle.close > state["last_vwap"]:
                state["internal_state"] = "INVALIDATED"
                state["market_state"] = "CHOP_ZONE"
                state["active_signal"] = {
                    "type": "STOP_LOSS_HIT",
                    "message": "Candle closed above VWAP. Thesis invalidated.",
                    "color": "rose"
                }

    async def _evaluate_state(self, instrument: str, state: Dict[str, Any], ltp: float):
        if state["last_vwap"] is None or state["current_st"] is None:
            # Need both to form bands
            state["active_signal"] = {
                "type": "WAIT",
                "message": "Waiting for VWAP and SuperTrend calculation.",
                "color": "slate"
            }
            await self._emit_state(instrument, state)
            return

        state["upper_band"] = max(state["last_vwap"], state["current_st"])
        state["lower_band"] = min(state["last_vwap"], state["current_st"])

        # If conviction is lost, reset everything to CHOP_ZONE
        if abs(state["oi_diff_pct"]) < 40.0:
            state["market_state"] = "CHOP_ZONE"
            state["internal_state"] = "WAITING"
            state["active_signal"] = {
                "type": "WAIT",
                "message": f"OI Conviction ({state['oi_diff_pct']}%) below 40% threshold.",
                "color": "slate"
            }
            await self._emit_state(instrument, state)
            return

        # Handle Bullish Flow
        if state["oi_diff_pct"] >= 40.0:
            if state["internal_state"] in ["WAITING", "INVALIDATED", "BEARISH_TREND_CONFIRMED", "BEARISH_TIER_1", "BEARISH_TIER_2"]:
                if ltp > state["upper_band"]:
                    state["market_state"] = "TRENDING_BULLISH"
                    state["internal_state"] = "BULLISH_TREND_CONFIRMED"
                    state["active_signal"] = {
                        "type": "WAIT",
                        "message": "Awaiting Pullback Setup.",
                        "color": "slate"
                    }
                else:
                    state["market_state"] = "CHOP_ZONE"
                    state["internal_state"] = "WAITING"
                    state["active_signal"] = {
                        "type": "WAIT",
                        "message": "Price trapped between VWAP and SuperTrend.",
                        "color": "slate"
                    }
            elif state["internal_state"] == "BULLISH_TREND_CONFIRMED":
                if ltp <= state["current_st"] * 1.0005:
                    state["internal_state"] = "BULLISH_TIER_1"
                    state["active_signal"] = {
                        "type": "BUY_TIER_1",
                        "message": "Scale In (Tier 1) at SuperTrend.",
                        "color": "emerald"
                    }
            elif state["internal_state"] == "BULLISH_TIER_1":
                if ltp <= state["last_vwap"] * 1.0005:
                    state["internal_state"] = "BULLISH_TIER_2"
                    state["active_signal"] = {
                        "type": "BUY_TIER_2",
                        "message": "Scale In (Tier 2) at VWAP.",
                        "color": "emerald"
                    }

        # Handle Bearish Flow
        elif state["oi_diff_pct"] <= -40.0:
            if state["internal_state"] in ["WAITING", "INVALIDATED", "BULLISH_TREND_CONFIRMED", "BULLISH_TIER_1", "BULLISH_TIER_2"]:
                if ltp < state["lower_band"]:
                    state["market_state"] = "TRENDING_BEARISH"
                    state["internal_state"] = "BEARISH_TREND_CONFIRMED"
                    state["active_signal"] = {
                        "type": "WAIT",
                        "message": "Awaiting Pullback Setup.",
                        "color": "slate"
                    }
                else:
                    state["market_state"] = "CHOP_ZONE"
                    state["internal_state"] = "WAITING"
                    state["active_signal"] = {
                        "type": "WAIT",
                        "message": "Price trapped between VWAP and SuperTrend.",
                        "color": "slate"
                    }
            elif state["internal_state"] == "BEARISH_TREND_CONFIRMED":
                if ltp >= state["current_st"] * 0.9995:
                    state["internal_state"] = "BEARISH_TIER_1"
                    state["active_signal"] = {
                        "type": "BUY_TIER_1",
                        "message": "Scale In Bearish (Tier 1) at SuperTrend.",
                        "color": "rose"
                    }
            elif state["internal_state"] == "BEARISH_TIER_1":
                if ltp >= state["last_vwap"] * 0.9995:
                    state["internal_state"] = "BEARISH_TIER_2"
                    state["active_signal"] = {
                        "type": "BUY_TIER_2",
                        "message": "Scale In Bearish (Tier 2) at VWAP.",
                        "color": "rose"
                    }

        await self._emit_state(instrument, state)

pullback_chop_filter_engine = PullbackChopFilterStrategy()
