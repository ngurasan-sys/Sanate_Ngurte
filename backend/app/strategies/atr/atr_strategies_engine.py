import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import pytz

from backend.app.core.event_bus import event_bus
from backend.app.market_data.models import Tick, Candle
from backend.app.oi.models import OITick

logger = logging.getLogger(__name__)

class ATRStrategiesEngine:
    def __init__(self):
        self.strategy_id = "atr_strategies"
        self.strategy_name = "ATR Strategies"

        # Configuration
        self.ENTRY_START = "09:45"
        self.ENTRY_END = "14:00"
        self.ATR_PERIOD = 14
        self.ATR_EXHAUSTION_RATIO = 1.0
        self.SUPERTREND_PERIOD = 10
        self.SUPERTREND_MULTIPLIER = 2.0
        self.VWAP_BUFFER = 8
        self.VOLUME_WMA_PERIOD = 20
        self.VOLUME_SPIKE_MULTIPLIER = 1.5
        self.TIER_1_LOTS = 2
        self.TIER_2_LOTS = 4
        self.PARTIAL_EXIT_LOTS = 2
        self.PARTIAL_PROFIT_POINTS = 20
        self.TRAILING_BUFFER = 10
        self.SUPERTREND_TOLERANCE = 5.0

        # Timezone
        self.tz = pytz.timezone('Asia/Kolkata')

        # Internal State
        self.running = False

        # Per-underlying state (e.g. NIFTY)
        # { underlying_symbol: { "state": "DISCOVERY" | "ACTIVE" | "LATE_SESSION", ... } }
        self.underlying_states: Dict[str, Dict[str, Any]] = {}

    def start(self):
        if self.running:
            return
        self.running = True

        # Subscriptions
        event_bus.subscribe("MARKET_TICK", self.on_market_tick)
        event_bus.subscribe("CANDLE_CLOSED", self.on_candle_closed)
        event_bus.subscribe("trending_oi", self.on_trending_oi)

        logger.info(f"Started {self.strategy_name} Engine")

    def stop(self):
        self.running = False
        logger.info(f"Stopped {self.strategy_name} Engine")

    def _get_underlying_state(self, underlying: str) -> Dict[str, Any]:
        if underlying not in self.underlying_states:
            self.underlying_states[underlying] = {
                "state": "WAITING",
                "futures_price": 0.0,
                "futures_oi": 0.0,
                "futures_oi_change": 0.0,
                "futures_volume": 0.0,
                "futures_volume_history": [],
                "vwap": 0.0,
                "supertrend": 0.0,
                "supertrend_direction": 1,
                "daily_atr": 0.0,
                "day_high": 0.0,
                "day_low": 0.0,
                "trending_oi_bullish": False,
                "trending_oi_bearish": False,
                "trending_oi_reason": "",
                "position": {
                    "active": False,
                    "direction": "",
                    "tier_1_filled": False,
                    "tier_2_filled": False,
                    "avg_entry_price": 0.0,
                    "lots_held": 0,
                    "current_sl": 0.0,
                    "partial_booked": False
                },
                "latest_3m_candle": None,
                "atr_st_history": [],
            }
        return self.underlying_states[underlying]

    def _update_session_state(self, underlying: str, dt: datetime):
        state = self._get_underlying_state(underlying)
        time_str = dt.strftime("%H:%M:%S")

        if time_str < "09:15:00":
            state["state"] = "WAITING"
        elif "09:15:00" <= time_str < self.ENTRY_START + ":00":
            state["state"] = "DISCOVERY"
        elif self.ENTRY_START + ":00" <= time_str < self.ENTRY_END + ":00":
            state["state"] = "ACTIVE"
        else:
            state["state"] = "LATE_SESSION"

    def _calculate_supertrend(self, state: Dict[str, Any], candle: Candle):
        # We need ATR for SuperTrend. Just a simple approximation for the test logic or full if needed.
        # We store High, Low, Close in atr_st_history.
        history = state["atr_st_history"]
        history.append(candle)
        if len(history) > self.SUPERTREND_PERIOD + 1:
            history.pop(0)

        if len(history) < self.SUPERTREND_PERIOD:
            return

        # Simplified ATR for SuperTrend
        tr_list = []
        for i in range(1, len(history)):
            prev = history[i-1]
            curr = history[i]
            tr1 = curr.high - curr.low
            tr2 = abs(curr.high - prev.close)
            tr3 = abs(curr.low - prev.close)
            tr_list.append(max(tr1, tr2, tr3))

        atr = sum(tr_list[-self.SUPERTREND_PERIOD:]) / self.SUPERTREND_PERIOD
        hl2 = (candle.high + candle.low) / 2
        basic_ub = hl2 + (self.SUPERTREND_MULTIPLIER * atr)
        basic_lb = hl2 - (self.SUPERTREND_MULTIPLIER * atr)

        if state["supertrend"] == 0.0:
            state["supertrend"] = basic_lb
            state["supertrend_direction"] = 1
            state["final_ub"] = basic_ub
            state["final_lb"] = basic_lb
        else:
            prev_close = history[-2].close
            prev_final_ub = state.get("final_ub", basic_ub)
            prev_final_lb = state.get("final_lb", basic_lb)

            final_ub = basic_ub if basic_ub < prev_final_ub or prev_close > prev_final_ub else prev_final_ub
            final_lb = basic_lb if basic_lb > prev_final_lb or prev_close < prev_final_lb else prev_final_lb

            state["final_ub"] = final_ub
            state["final_lb"] = final_lb

            direction = state["supertrend_direction"]
            if direction == 1 and candle.close < final_lb:
                direction = -1
            elif direction == -1 and candle.close > final_ub:
                direction = 1

            state["supertrend_direction"] = direction
            state["supertrend"] = final_lb if direction == 1 else final_ub

    async def on_market_tick(self, tick: Tick):
        if not self.running:
            return

        # Simplistic mapping of futures logic
        if "FUT" in tick.instrument:
            underlying = tick.instrument.split("FUT")[0].replace("NSE_INDEX|", "").replace("NSE_FO|", "").strip("- ")
            # Just extract basic symbol if possible, assuming test format or generic
            if "NIFTY" in tick.instrument and "BANK" not in tick.instrument and "MID" not in tick.instrument and "FIN" not in tick.instrument: underlying = "NIFTY"
            elif "BANKNIFTY" in tick.instrument: underlying = "BANKNIFTY"

            state = self._get_underlying_state(underlying)
            self._update_session_state(underlying, tick.timestamp)

            # Update Day High/Low
            if state["day_high"] == 0.0 or tick.price > state["day_high"]: state["day_high"] = tick.price
            if state["day_low"] == 0.0 or tick.price < state["day_low"]: state["day_low"] = tick.price

            state["futures_price"] = tick.price
            # PERFORMANCE OPTIMIZATION: Use try...except instead of hasattr to avoid overhead in performance-critical hot paths
            try:
                state["futures_oi_change"] = tick.oi - state["futures_oi"]
                state["futures_oi"] = tick.oi
            except AttributeError:
                pass

            if tick.volume:
                state["futures_volume"] = tick.volume

            # Trigger live evaluation (for stop losses etc, or VWAP dips)
            await self._evaluate_position(underlying, tick)

    async def on_candle_closed(self, candle: Candle):
        if not self.running:
            return

        # Parse underlying (simplistic)
        underlying = candle.instrument
        if "FUT" in candle.instrument or "NIFTY" in candle.instrument:
             if "NIFTY" in candle.instrument and "BANK" not in candle.instrument and "MID" not in candle.instrument and "FIN" not in candle.instrument: underlying = "NIFTY"
             elif "BANKNIFTY" in candle.instrument: underlying = "BANKNIFTY"

        state = self._get_underlying_state(underlying)
        self._update_session_state(underlying, candle.timestamp)

        if candle.timeframe == "1440m":
             # Daily candle for ATR
             tr = candle.high - candle.low
             if "daily_atr_history" not in state: state["daily_atr_history"] = []
             state["daily_atr_history"].append(tr)
             if len(state["daily_atr_history"]) > self.ATR_PERIOD: state["daily_atr_history"].pop(0)
             state["daily_atr"] = sum(state["daily_atr_history"]) / len(state["daily_atr_history"])
             return

        if candle.timeframe == "3m":
            state["latest_3m_candle"] = candle
            if candle.vwap:
                state["vwap"] = candle.vwap
            self._calculate_supertrend(state, candle)

            # Volume WMA
            state["futures_volume_history"].append(candle.volume)
            if len(state["futures_volume_history"]) > self.VOLUME_WMA_PERIOD:
                state["futures_volume_history"].pop(0)

            # Evaluate new entries on candle close
            await self._evaluate_entries(underlying, candle)

    async def on_trending_oi(self, event: Dict[str, Any]):
        if not self.running:
            return

        if event.get("type") == "tick_update" and event.get("view") == "spot_trending_oi":
            underlying = event.get("underlying", "NIFTY")
            state = self._get_underlying_state(underlying)
            row = event.get("row", {})

            direction_pct = row.get("directionPercent", 0.0)
            diff_oi = row.get("differenceOi", 0.0)
            call_oi_chg = row.get("changeCeOi", 0.0)
            put_oi_chg = row.get("changePeOi", 0.0)

            # Reset
            state["trending_oi_bullish"] = False
            state["trending_oi_bearish"] = False

            # Bullish: >= +40% OR (Call OI < 0 AND Put OI > 0)
            if direction_pct >= 40.0:
                state["trending_oi_bullish"] = True
                state["trending_oi_reason"] = "TRENDING_OI"
            elif call_oi_chg < 0 and put_oi_chg > 0:
                state["trending_oi_bullish"] = True
                state["trending_oi_reason"] = "CALL_OI_SHORT_COVERING"

            # Bearish: <= -40%
            if direction_pct <= -40.0:
                state["trending_oi_bearish"] = True
                state["trending_oi_reason"] = "TRENDING_OI"

    def _is_atr_exhausted(self, state: Dict[str, Any]) -> bool:
        if state["daily_atr"] <= 0:
            return False # Fallback or wait for data
        intraday_range = state["day_high"] - state["day_low"]
        return (intraday_range / state["daily_atr"]) >= self.ATR_EXHAUSTION_RATIO

    def _get_volume_wma(self, state: Dict[str, Any]) -> float:
        history = state["futures_volume_history"]
        n = len(history)
        if n == 0: return 0.0
        weight_sum = (n * (n + 1)) / 2
        wma = sum(history[i] * (i + 1) for i in range(n)) / weight_sum
        return wma

    async def _evaluate_entries(self, underlying: str, candle: Candle):
        state = self._get_underlying_state(underlying)

        if state["state"] != "ACTIVE":
            return

        if self._is_atr_exhausted(state):
            return

        if state["position"]["active"]:
            return # Manage in evaluate_position

        # Confluence Checks
        vol_wma = self._get_volume_wma(state)
        vol_spike = candle.volume >= (self.VOLUME_SPIKE_MULTIPLIER * vol_wma) if vol_wma > 0 else False

        bullish_futures_sc = (state["futures_oi_change"] < 0) and (candle.close > candle.open) and vol_spike
        bearish_futures_lu = (state["futures_oi_change"] < 0) and (candle.close < candle.open) and vol_spike # Simplistic Bearish Conf

        # Pullback check
        supertrend = state["supertrend"]
        is_bullish_pullback = (candle.low <= supertrend + self.SUPERTREND_TOLERANCE) and (candle.close >= supertrend)
        is_bearish_pullback = (candle.high >= supertrend - self.SUPERTREND_TOLERANCE) and (candle.close <= supertrend)

        # Bullish Entry
        if state["trending_oi_bullish"] and bullish_futures_sc and vol_spike and state["supertrend_direction"] == 1 and is_bullish_pullback:
            await self._enter_tier_1(underlying, "BUY_CE", candle, "Bullish Trending OI + Futures short covering + 1.5x volume WMA + SuperTrend pullback")

        # Bearish Entry
        elif state["trending_oi_bearish"] and bearish_futures_lu and vol_spike and state["supertrend_direction"] == -1 and is_bearish_pullback:
            await self._enter_tier_1(underlying, "BUY_PE", candle, "Bearish Trending OI + Futures confirmation + 1.5x volume WMA + SuperTrend pullback")

    async def _enter_tier_1(self, underlying: str, action: str, candle: Candle, reason: str):
        state = self._get_underlying_state(underlying)
        pos = state["position"]
        pos["active"] = True
        pos["direction"] = action
        pos["tier_1_filled"] = True
        pos["avg_entry_price"] = candle.close # Using Futures price as a proxy for test logic if option isn't resolved here
        pos["lots_held"] = self.TIER_1_LOTS
        pos["current_sl"] = candle.low - self.TRAILING_BUFFER if action == "BUY_CE" else candle.high + self.TRAILING_BUFFER

        await self._emit_signal(underlying, action, self.TIER_1_LOTS, reason, state, candle)

    async def _evaluate_position(self, underlying: str, tick: Tick):
        state = self._get_underlying_state(underlying)
        pos = state["position"]
        if not pos["active"]:
            return

        current_price = tick.price
        vwap = state["vwap"]

        # We need a dummy candle obj for emit_signal which expects a Candle
        dummy_candle = Candle(
            instrument=tick.instrument, timeframe="0", timestamp=tick.timestamp,
            open=tick.price, high=tick.price, low=tick.price, close=tick.price, volume=tick.volume or 0
        )

        # 1. Hard Invalidation (VWAP)
        if vwap > 0:
            if pos["direction"] == "BUY_CE" and current_price <= (vwap - self.VWAP_BUFFER):
                await self._exit_all(underlying, dummy_candle, "VWAP_ZONE_INVALIDATED")
                return
            elif pos["direction"] == "BUY_PE" and current_price >= (vwap + self.VWAP_BUFFER):
                await self._exit_all(underlying, dummy_candle, "VWAP_ZONE_INVALIDATED")
                return

        # 2. Tier 2 Entry (VWAP Dip)
        if pos["tier_1_filled"] and not pos["tier_2_filled"] and vwap > 0:
            tier_2_triggered = False
            if pos["direction"] == "BUY_CE" and current_price <= (vwap + self.VWAP_BUFFER) and current_price > (vwap - self.VWAP_BUFFER):
                tier_2_triggered = True
            elif pos["direction"] == "BUY_PE" and current_price >= (vwap - self.VWAP_BUFFER) and current_price < (vwap + self.VWAP_BUFFER):
                tier_2_triggered = True

            if tier_2_triggered:
                # Weighted Average
                old_qty = pos["lots_held"]
                old_avg = pos["avg_entry_price"]
                new_qty = self.TIER_2_LOTS
                new_price = current_price

                pos["lots_held"] += new_qty
                pos["avg_entry_price"] = ((old_qty * old_avg) + (new_qty * new_price)) / pos["lots_held"]
                pos["tier_2_filled"] = True

                await self._emit_signal(underlying, "ADD_TIER_2", new_qty, "VWAP dip entry", state, dummy_candle)

        # 3. Partial Profit
        if not pos["partial_booked"]:
            target_hit = False
            if pos["direction"] == "BUY_CE" and current_price >= (pos["avg_entry_price"] + self.PARTIAL_PROFIT_POINTS):
                target_hit = True
            elif pos["direction"] == "BUY_PE" and current_price <= (pos["avg_entry_price"] - self.PARTIAL_PROFIT_POINTS):
                target_hit = True

            if target_hit:
                pos["partial_booked"] = True
                exit_lots = min(self.PARTIAL_EXIT_LOTS, pos["lots_held"])
                pos["lots_held"] -= exit_lots
                pos["current_sl"] = pos["avg_entry_price"] # Break even

                await self._emit_signal(underlying, "EXIT_PARTIAL", exit_lots, "PARTIAL_PROFIT_BREAK_EVEN", state, dummy_candle)

                if pos["lots_held"] <= 0:
                    self._reset_position(pos)
                    return

        # 4. Trailing Stop
        if pos["partial_booked"]:
            latest_candle = state["latest_3m_candle"]
            if latest_candle:
                if pos["direction"] == "BUY_CE":
                    new_sl = latest_candle.low - self.TRAILING_BUFFER
                    if new_sl > pos["current_sl"]:
                        pos["current_sl"] = new_sl
                        await self._emit_signal(underlying, "TRAIL_SL", pos["lots_held"], "Trailing stop updated", state, dummy_candle)
                elif pos["direction"] == "BUY_PE":
                    new_sl = latest_candle.high + self.TRAILING_BUFFER
                    if new_sl < pos["current_sl"] or pos["current_sl"] == pos["avg_entry_price"]: # special handling for PE trailing logic
                        if pos["current_sl"] == pos["avg_entry_price"] and new_sl > pos["current_sl"]:
                             pass
                        else:
                             pos["current_sl"] = new_sl
                             await self._emit_signal(underlying, "TRAIL_SL", pos["lots_held"], "Trailing stop updated", state, dummy_candle)

        # 5. Stop Loss Hit check
        sl_hit = False
        if pos["direction"] == "BUY_CE" and pos["current_sl"] > 0 and current_price <= pos["current_sl"]:
            sl_hit = True
        elif pos["direction"] == "BUY_PE" and pos["current_sl"] > 0 and current_price >= pos["current_sl"]:
            sl_hit = True

        if sl_hit:
            await self._exit_all(underlying, dummy_candle, "STOP_LOSS_HIT")

    async def _exit_all(self, underlying: str, candle: Candle, reason: str):
        state = self._get_underlying_state(underlying)
        pos = state["position"]
        if pos["lots_held"] > 0:
            await self._emit_signal(underlying, "EXIT_ALL", pos["lots_held"], reason, state, candle)
        self._reset_position(pos)

    def _reset_position(self, pos: Dict[str, Any]):
        pos["active"] = False
        pos["direction"] = ""
        pos["tier_1_filled"] = False
        pos["tier_2_filled"] = False
        pos["avg_entry_price"] = 0.0
        pos["lots_held"] = 0
        pos["current_sl"] = 0.0
        pos["partial_booked"] = False

    async def _emit_signal(self, underlying: str, action: str, lots: int, reason: str, state: Dict[str, Any], candle: Candle):
        # Allow emitting signals even if candle is None or missing close property
        close_price = 0.0
        # PERFORMANCE OPTIMIZATION: Use try...except instead of hasattr to avoid overhead in performance-critical hot paths
        if candle:
            try:
                close_price = candle.close
            except AttributeError:
                pass

        signal = {
            "signal_id": f"SIG_{self.strategy_id}_{datetime.now().timestamp()}",
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "symbol": underlying,
            "underlying": underlying,
            "action": action,
            "instrument_key": "OPT_PROXY",
            "strike_price": 0,
            "option_type": "CE" if "CE" in action else "PE",
            "expiry": "",
            "underlying_price": close_price,
            "option_price": close_price,
            "lots": lots,
            "stop_loss": state["position"]["current_sl"],
            "avg_entry_price": state["position"]["avg_entry_price"],
            "daily_atr": state["daily_atr"],
            "vwap": state["vwap"],
            "supertrend": state["supertrend"],
            "reason": reason,
            "timestamp": datetime.now()
        }
        await event_bus.publish("STRATEGY_SIGNAL", signal)
