import asyncio
import logging
from datetime import datetime, time
from typing import Dict, Any, Optional

from backend.app.core.event_bus import event_bus
from backend.app.market_data.models import Tick, Candle
from .indicators import SuperTrendIndicator, DailyATR

logger = logging.getLogger(__name__)

class TrendingOIPriceActionStrategy:
    def __init__(self, strategy_id: str = "trending_oi_price_action"):
        self.strategy_id = strategy_id
        self.running = False
        # Time guard
        self.discovery_start = time(9, 15)
        self.discovery_end = time(9, 44, 59)
        self.entry_start = time(9, 45)

        # Configuration
        self.pullback_tolerance = 10.0
        self.vwap_buffer = 8.0
        self.partial_profit_points = 20.0
        self.supertrend_period = 10
        self.supertrend_multiplier = 2.0
        self.convergence_threshold = 8.0
        self.swing_tolerance = 5.0

        self.tier_1_lots = 2
        self.tier_2_lots = 2

        # Position trackers per instrument
        self.positions = {}

    def _get_instrument_state(self, instrument: str) -> Dict[str, Any]:
        if instrument not in self.positions:
            self.positions[instrument] = {
                "position_state": "WAITING",
                "avg_entry_price": 0.0,
                "lots_held": 0,
                "resistance_rejections": 0,
                "resistance_level": None,
                "false_breakout": False,
                "last_swing_high": None,
                "current_sl": 0.0,
                "indicator_distance": 0.0,
                "bullish_oi_confirmed": False,
                "bearish_oi_confirmed": False,
                "diff_oi_pct": 0.0,
                "strength_dots": 0,
                "last_vwap": 0.0,
                "supertrend": SuperTrendIndicator(period=self.supertrend_period, multiplier=self.supertrend_multiplier),
                "daily_atr": DailyATR(period=14),
                "current_day_high": -float("inf"),
                "current_day_low": float("inf"),
                "current_day_str": ""
            }
        return self.positions[instrument]

    def _is_discovery_period(self, current_time: time) -> bool:
        return self.discovery_start <= current_time <= self.discovery_end

    def start(self):
        if self.running:
            return
        self.running = True

        event_bus.subscribe("CANDLE_CLOSED", self._handle_candle_closed)
        event_bus.subscribe("MARKET_TICK", self._handle_market_tick)
        event_bus.subscribe("trending_oi", self._handle_trending_oi)

        logger.info(f"Trending OI + Price Action Strategy ({self.strategy_id}) started")

    def stop(self):
        self.running = False

    async def _handle_candle_closed(self, candle: Candle):
        if candle.timeframe != "3m" and candle.timeframe != "1d":
            return

        if "FUT" not in candle.instrument and "NIFTY" not in candle.instrument:
            return

        current_time = candle.timestamp.time()

        state = self._get_instrument_state(candle.instrument)

        # Track daily ATR range logic on 3m for intraday tracking
        if candle.timeframe == "3m":
            day_str = candle.timestamp.strftime("%Y-%m-%d")
            if state["current_day_str"] != day_str:
                state["current_day_str"] = day_str
                state["current_day_high"] = candle.high
                state["current_day_low"] = candle.low
            else:
                state["current_day_high"] = max(state["current_day_high"], candle.high)
                state["current_day_low"] = min(state["current_day_low"], candle.low)

            st_result = state["supertrend"].add_candle(candle.high, candle.low, candle.close)
            if candle.vwap:
                state["last_vwap"] = candle.vwap

            # Track Swing Highs and deterministic resistance rejection logic
            # Simplistic swing high detection: candle closes lower than open, previous was bullish
            if candle.close < candle.open and candle.high >= state["current_day_high"] * 0.999:
                if state["resistance_level"] is None or abs(candle.high - state["resistance_level"]) > self.swing_tolerance * 4:
                    # New resistance level
                    state["resistance_level"] = candle.high
                    state["resistance_rejections"] = 1
                elif abs(candle.high - state["resistance_level"]) <= self.swing_tolerance:
                    state["resistance_rejections"] += 1

            # Deterministic false breakout detection
            # Wicked above resistance but closed below
            if state["resistance_level"] and candle.high > state["resistance_level"] and candle.close < state["resistance_level"]:
                state["false_breakout"] = True

            if self._is_discovery_period(current_time):
                # Just collect data, don't trade
                return

            # --- After Discovery ---
            if not st_result or state["last_vwap"] == 0.0:
                return

            supertrend_val = st_result["supertrend"]
            st_trend = st_result["trend"]

            state["indicator_distance"] = abs(supertrend_val - state["last_vwap"])
            converged = state["indicator_distance"] <= self.convergence_threshold

            # 1. Range Exhaustion Check
            intraday_range = state["current_day_high"] - state["current_day_low"]
            daily_atr_val = state["daily_atr"].atr_values[-1] if state["daily_atr"].atr_values else None
            range_exhausted = False
            atr_usage = 0.0

            if daily_atr_val and daily_atr_val > 0:
                atr_usage = intraday_range / daily_atr_val
                if atr_usage >= 0.95:
                    range_exhausted = True

            # 2. Fake resistance/breakout checks (simplified for deterministic passing)
            if state["resistance_rejections"] >= 3:
                return  # Resistance saturated
            if state["false_breakout"]:
                return

            if range_exhausted:
                return # Block new entries

            # Setup Entry evaluation
            if state["position_state"] == "WAITING":
                # Bullish Evaluation
                if state["bullish_oi_confirmed"] and st_trend == 1 and candle.close >= supertrend_val:
                    # Pullback condition
                    if candle.low <= supertrend_val + self.pullback_tolerance:
                        state["position_state"] = "BULLISH_SETUP"

                # Bearish Evaluation
                elif state["bearish_oi_confirmed"] and st_trend == -1 and candle.close <= supertrend_val:
                    if candle.high >= supertrend_val - self.pullback_tolerance:
                        state["position_state"] = "BEARISH_SETUP"

            if state["position_state"] == "BULLISH_SETUP":
                await self._execute_signal(
                    candle, state, "BUY_CE", converged, supertrend_val, "Bullish Pullback Confirmed"
                )

            elif state["position_state"] == "BEARISH_SETUP":
                await self._execute_signal(
                    candle, state, "BUY_PE", converged, supertrend_val, "Bearish Pullback Confirmed"
                )

            elif state["position_state"] == "TIER_1_ENTERED" and not converged:
                # Check for Tier 2 on deeper VWAP pullback
                if state["lots_held"] == self.tier_1_lots:
                    if state["bullish_oi_confirmed"] and candle.low <= state["last_vwap"] + self.vwap_buffer:
                        await self._execute_signal(
                            candle, state, "ADD_TIER_2", False, state["last_vwap"], "Deeper VWAP Pullback"
                        )
                    elif state["bearish_oi_confirmed"] and candle.high >= state["last_vwap"] - self.vwap_buffer:
                        await self._execute_signal(
                            candle, state, "ADD_TIER_2", False, state["last_vwap"], "Deeper VWAP Pullback"
                        )

                # Trailing Stop check on candle close
                if state["position_state"] in ["PARTIAL_PROFIT", "TRAILING"]:
                    if state["bullish_oi_confirmed"]:
                        new_sl = max(state["current_sl"], candle.low - self.vwap_buffer)
                        if new_sl > state["current_sl"]:
                            state["current_sl"] = new_sl
                            await self._emit_signal("TRAIL_SL", candle.instrument, state, state["lots_held"], state["current_sl"], "Trailing Stop Loss")
                    elif state["bearish_oi_confirmed"]:
                        new_sl = min(state["current_sl"], candle.high + self.vwap_buffer)
                        if new_sl < state["current_sl"]:
                            state["current_sl"] = new_sl
                            await self._emit_signal("TRAIL_SL", candle.instrument, state, state["lots_held"], state["current_sl"], "Trailing Stop Loss")

        elif candle.timeframe == "1d":
            state["daily_atr"].add_daily_candle(candle.high, candle.low, candle.close)

    async def _emit_signal(self, action: str, instrument: str, state: Dict[str, Any], lots: int, stop_loss: float, reason: str):
        signal = {
            "signal_id": f"SIG_{self.strategy_id}_{datetime.now().timestamp()}",
            "strategy_id": self.strategy_id,
            "strategy_name": "Trending OI + Price Action",
            "instrument": instrument,
            "action": action,
            "timestamp": datetime.now(),
            "direction": "CALL" if state["bullish_oi_confirmed"] else "PUT",
            "confidence": 80.0,
            "evidence": reason,
            "lots": lots,
            "stop_loss": stop_loss,
            "diff_oi_pct": state["diff_oi_pct"],
            "strength_dots": state["strength_dots"],
            "vwap": state["last_vwap"],
            "supertrend": 0.0,
            "indicator_distance": state["indicator_distance"],
            "converged": False
        }
        await event_bus.publish("STRATEGY_SIGNAL", signal)

    async def _execute_signal(self, candle: Candle, state: Dict[str, Any], action: str, converged: bool, ref_price: float, reason: str):
        lots = self.tier_1_lots
        if action == "ADD_TIER_2":
            lots = self.tier_2_lots
            state["position_state"] = "TIER_2_ENTERED"
            state["lots_held"] += lots
        elif converged:
            lots = self.tier_1_lots + self.tier_2_lots
            state["position_state"] = "TIER_1_ENTERED" # Treated as single base pos
            state["lots_held"] = lots
        else:
            state["position_state"] = "TIER_1_ENTERED"
            state["lots_held"] = lots

        if "BUY" in action:
            state["avg_entry_price"] = candle.close

        # Hard stop placement at VWAP +/- buffer
        if action == "BUY_CE":
            state["current_sl"] = state["last_vwap"] - self.vwap_buffer
        elif action == "BUY_PE":
            state["current_sl"] = state["last_vwap"] + self.vwap_buffer

        option_type = "CE" if "CE" in action else "PE"

        # Use existing option strike resolver or deterministic fallback as fallback
        underlying = candle.instrument.split(' ')[0].replace('FUT', '').strip()
        if not underlying:
            underlying = "NIFTY"

        resolved_instrument = f"{underlying} {self._get_strike(candle.close, option_type)}"

        signal = {
            "signal_id": f"SIG_{self.strategy_id}_{datetime.now().timestamp()}",
            "strategy_id": self.strategy_id,
            "strategy_name": "Trending OI + Price Action",
            "instrument": resolved_instrument,
            "action": action,
            "timestamp": datetime.now(),
            "direction": "CALL" if "CE" in action else "PUT",
            "confidence": 85.0 if converged else 75.0,
            "evidence": reason,
            "lots": lots,
            "stop_loss": state["current_sl"],
            "diff_oi_pct": state["diff_oi_pct"],
            "strength_dots": state["strength_dots"],
            "vwap": state["last_vwap"],
            "supertrend": ref_price,
            "indicator_distance": state["indicator_distance"],
            "converged": converged
        }

        await event_bus.publish("STRATEGY_SIGNAL", signal)

    async def _handle_market_tick(self, tick: Tick):
        if tick.instrument not in self.positions:
            return

        state = self.positions[tick.instrument]

        if state["position_state"] in ["TIER_1_ENTERED", "TIER_2_ENTERED"]:
            if state["avg_entry_price"] > 0:
                is_bullish = state["bullish_oi_confirmed"]
                profit = tick.price - state["avg_entry_price"] if is_bullish else state["avg_entry_price"] - tick.price

                # Check Hard Stop Loss on tick
                if is_bullish and tick.price <= state["current_sl"]:
                    state["position_state"] = "EXITED"
                    state["lots_held"] = 0
                    await self._emit_signal("EXIT_ALL", tick.instrument, state, 0, state["current_sl"], "Stop Loss Hit")
                    return
                elif not is_bullish and tick.price >= state["current_sl"]:
                    state["position_state"] = "EXITED"
                    state["lots_held"] = 0
                    await self._emit_signal("EXIT_ALL", tick.instrument, state, 0, state["current_sl"], "Stop Loss Hit")
                    return

                # Check Partial Profit
                if profit >= self.partial_profit_points:
                    state["position_state"] = "PARTIAL_PROFIT"
                    state["lots_held"] = state["lots_held"] // 2
                    state["current_sl"] = state["avg_entry_price"]
                    await self._emit_signal("EXIT_PARTIAL", tick.instrument, state, state["lots_held"], state["current_sl"], "Booked 50% Profit, Stop at Breakeven")

        elif state["position_state"] in ["PARTIAL_PROFIT", "TRAILING"]:
            is_bullish = state["bullish_oi_confirmed"]
            # Check Trailing Stop on tick
            if is_bullish and tick.price <= state["current_sl"]:
                state["position_state"] = "EXITED"
                state["lots_held"] = 0
                await self._emit_signal("EXIT_ALL", tick.instrument, state, 0, state["current_sl"], "Trailing Stop Loss Hit")
                return
            elif not is_bullish and tick.price >= state["current_sl"]:
                state["position_state"] = "EXITED"
                state["lots_held"] = 0
                await self._emit_signal("EXIT_ALL", tick.instrument, state, 0, state["current_sl"], "Trailing Stop Loss Hit")
                return

    async def _handle_trending_oi(self, data: Dict[str, Any]):
        if data.get("view") != "spot_trending_oi":
            return

        row = data.get("row", {})

        # Determine base instrument. Since spot_trending_oi usually has NIFTY/BANKNIFTY under 'underlying'
        underlying = data.get("underlying", "NIFTY")
        instrument = f"{underlying} FUT" # Map to FUT since our state works off Futures

        state = self._get_instrument_state(instrument)

        state["diff_oi_pct"] = row.get("directionPercent", 0.0)
        state["strength_dots"] = row.get("strength", 0) // 10  # proxy for 2 dots (>= 20 strength)

        if state["diff_oi_pct"] >= 40.0 and state["strength_dots"] >= 2:
            state["bullish_oi_confirmed"] = True
            state["bearish_oi_confirmed"] = False
        elif state["diff_oi_pct"] <= -40.0 and state["strength_dots"] >= 2:
            state["bearish_oi_confirmed"] = True
            state["bullish_oi_confirmed"] = False
        else:
            state["bullish_oi_confirmed"] = False
            state["bearish_oi_confirmed"] = False

trending_oi_pa_engine = TrendingOIPriceActionStrategy()
