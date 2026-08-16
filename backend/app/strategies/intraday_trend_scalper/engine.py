import asyncio
import logging
from datetime import datetime, time, date
from typing import Dict, Any, Optional

from backend.app.core.event_bus import event_bus
from backend.app.market_data.models import Tick, Candle
from backend.app.strategies.gap_opening.strike_selection import StrikeSelectionService
from backend.app.strategies.trending_oi_price_action.indicators import SuperTrendIndicator

logger = logging.getLogger(__name__)

class IntradayTrendScalper:
    def __init__(self, strategy_id: str = "intraday_trend_scalper"):
        self.strategy_id = strategy_id
        self.running = False

        # Configuration
        self.strategy_start_time = time(9, 30)
        self.new_entry_cutoff = time(14, 0)
        self.max_daily_trades = 3

        self.bullish_oi_difference_threshold = 4_000_000

        self.tier_1_lots = 2
        self.tier_2_lots = 4
        self.tier_3_lots = 8

        self.stop_buffer_points = 5.0
        self.partial_profit_points = 20.0  # arbitrary configurable trigger point

        self.supertrend_period = 10
        self.supertrend_multiplier = 2.0

        # State per instrument
        self.positions: Dict[str, Dict[str, Any]] = {}

        # Daily accounting per session
        self.current_date: Optional[date] = None
        self.daily_trades_count = 0
        self._publish_task = None

    def start(self):
        if self.running:
            return
        self.running = True

        event_bus.subscribe("CANDLE_CLOSED", self._handle_candle_closed)
        event_bus.subscribe("MARKET_TICK", self._handle_market_tick)
        event_bus.subscribe("trending_oi", self._handle_trending_oi)

        try:
            asyncio.get_running_loop()
            self._publish_task = asyncio.create_task(self._publish_loop())
        except RuntimeError:
            # We are not in a running loop, likely in a synchronous test context
            pass
        logger.info(f"Intraday Trend Scalper ({self.strategy_id}) started")

    def stop(self):
        self.running = False
        if self._publish_task:
            self._publish_task.cancel()

    def _reset_daily_state(self, current_day: date):
        self.current_date = current_day
        self.daily_trades_count = 0
        for instrument in self.positions:
            self.positions[instrument]["daily_trades_count"] = 0
            self.positions[instrument]["state"] = "IDLE"

    def _get_instrument_state(self, instrument: str) -> Dict[str, Any]:
        if instrument not in self.positions:
            self.positions[instrument] = {
                "state": "IDLE",  # IDLE, WAITING_FOR_OPEN, SCANNING, BULLISH_TREND_CONFIRMED, BEARISH_TREND_CONFIRMED, AWAITING_PULLBACK, ENTRY_TIER_1, ENTRY_TIER_2, ENTRY_TIER_3, PROFIT_PROTECTION, BREAK_EVEN, TRAILING, EXITED, NO_TRADE_ZONE, INVALIDATED
                "daily_trades_count": self.daily_trades_count,

                "avg_entry_price": 0.0,
                "current_sl": 0.0,
                "lots_held": 0,

                "bullish_oi_confirmed": False,
                "bearish_oi_confirmed": False,
                "diff_oi": 0.0,

                "last_vwap": 0.0,
                "supertrend": 0.0,
                "trend": 0, # 1 bullish, -1 bearish
                "current_day_high": -float("inf"),
                "current_day_low": float("inf"),
                "supertrend_indicator": SuperTrendIndicator(period=self.supertrend_period, multiplier=self.supertrend_multiplier),

                # Setup specific state
                "breakout_level": 0.0,
                "pullback_level": 0.0,
                "break_even_activated": False,
                "partial_profit_taken": False,
                "entry_tier_1_price": 0.0,
                "position_direction": 0, # 1 for CE, -1 for PE

                "next_action": "Waiting for market open."
            }
        return self.positions[instrument]

    async def _handle_candle_closed(self, candle: Candle):
        if candle.timeframe != "3m":
            return

        if "FUT" not in candle.instrument and "NIFTY" not in candle.instrument:
            return

        current_time = candle.timestamp.time()
        current_day = candle.timestamp.date()

        if self.current_date != current_day:
            self._reset_daily_state(current_day)

        state = self._get_instrument_state(candle.instrument)

        # Store previous day high before updating it to detect true breakouts
        previous_day_high = state["current_day_high"]
        previous_day_low = state["current_day_low"]

        # Update Daily High/Low
        state["current_day_high"] = max(state["current_day_high"], candle.high)
        state["current_day_low"] = min(state["current_day_low"], candle.low)

        # Update Indicators
        if candle.vwap:
            state["last_vwap"] = candle.vwap

        st_result = state["supertrend_indicator"].add_candle(candle.high, candle.low, candle.close)
        if st_result:
            state["supertrend"] = st_result["supertrend"]
            state["trend"] = st_result["trend"]

        if current_time < self.strategy_start_time:
            state["state"] = "WAITING_FOR_OPEN"
            state["next_action"] = "Waiting for 09:30."
            return

        if self.daily_trades_count >= self.max_daily_trades:
            if state["state"] in ["IDLE", "WAITING_FOR_OPEN", "SCANNING", "BULLISH_TREND_CONFIRMED", "BEARISH_TREND_CONFIRMED", "AWAITING_PULLBACK"]:
                state["state"] = "DAILY_LIMIT_REACHED"
                state["next_action"] = "Max daily trades reached."
                return
            # Existing positions can continue

        if current_time >= self.new_entry_cutoff:
            if state["state"] in ["IDLE", "WAITING_FOR_OPEN", "SCANNING", "BULLISH_TREND_CONFIRMED", "BEARISH_TREND_CONFIRMED", "AWAITING_PULLBACK"]:
                state["state"] = "TIME_BLOCKED"
                state["next_action"] = "Past 14:00 cutoff."
                return

        # Note: If already caught above and returned, we won't hit this.
        # But if it's DAILY_LIMIT_REACHED or TIME_BLOCKED, we don't want to fall into SCANNING
        if state["state"] in ["IDLE", "WAITING_FOR_OPEN", "SCANNING"]:
            state["state"] = "SCANNING"
            state["next_action"] = "Scanning for trend confirmation."

            # Requires OI conviction, indicators, AND breaking the day high/low
            # Use previous_day_high because if candle.close is the new high, candle.close == state["current_day_high"]
            # To be a true breakout, it must exceed the PREVIOUS recorded day high
            if (state["bullish_oi_confirmed"] and state["trend"] == 1 and
                candle.close > state["last_vwap"] and candle.close > state["supertrend"] and
                candle.close > previous_day_high):
                # Confirmed bullish breakout
                state["state"] = "BULLISH_TREND_CONFIRMED"
                state["next_action"] = "Bullish trend confirmed. Waiting for pullback."
            elif (state["bearish_oi_confirmed"] and state["trend"] == -1 and
                  candle.close < state["last_vwap"] and candle.close < state["supertrend"] and
                  candle.close < previous_day_low):
                # Confirmed bearish breakout
                state["state"] = "BEARISH_TREND_CONFIRMED"
                state["next_action"] = "Bearish trend confirmed. Waiting for pullback."

        elif state["state"] in ["BULLISH_TREND_CONFIRMED", "BEARISH_TREND_CONFIRMED", "AWAITING_PULLBACK"]:
            # Check No Trade Zone (SuperTrend and VWAP conflicting)
            if (state["trend"] == -1 and candle.close > state["last_vwap"]) or (state["trend"] == 1 and candle.close < state["last_vwap"]):
                state["state"] = "NO_TRADE_ZONE"
                state["next_action"] = "Price in congestion zone."
                return

            # Pullback Detection
            if state["state"] == "BULLISH_TREND_CONFIRMED":
                state["state"] = "AWAITING_PULLBACK"

            elif state["state"] == "BEARISH_TREND_CONFIRMED":
                state["state"] = "AWAITING_PULLBACK"

            if state["state"] == "AWAITING_PULLBACK":
                # Ensure conviction is still there
                if state["bullish_oi_confirmed"]:
                    if candle.low <= state["last_vwap"] + self.stop_buffer_points:
                        # Reached VWAP for pullback
                        # Initial stop at Day Low
                        initial_stop = state["current_day_low"] - self.stop_buffer_points
                        state["position_direction"] = 1
                        await self._execute_entry(candle.instrument, state, "ENTRY_TIER_1", self.tier_1_lots, candle.close, initial_stop)
                elif state["bearish_oi_confirmed"]:
                    if candle.high >= state["last_vwap"] - self.stop_buffer_points:
                        # Initial stop at Day High
                        initial_stop = state["current_day_high"] + self.stop_buffer_points
                        state["position_direction"] = -1
                        await self._execute_entry(candle.instrument, state, "ENTRY_TIER_1", self.tier_1_lots, candle.close, initial_stop)
                else:
                    state["state"] = "SCANNING"
                    state["next_action"] = "Conviction lost. Scanning again."

        elif state["state"] in ["ENTRY_TIER_1", "ENTRY_TIER_2", "ENTRY_TIER_3", "PROFIT_PROTECTION", "BREAK_EVEN", "TRAILING"]:
            is_bullish = state["position_direction"] == 1

            # Strict VWAP Invalidation Check (Candle Close)
            if is_bullish and candle.close < state["last_vwap"]:
                lots_before_exit = state["lots_held"]
                state["state"] = "INVALIDATED"
                state["lots_held"] = 0
                state["next_action"] = "Invalidated: Closed below VWAP."
                await self._emit_signal(candle.instrument, "EXIT_ALL", state, lots_before_exit, state["current_sl"], state["next_action"])
                return
            elif not is_bullish and candle.close > state["last_vwap"]:
                lots_before_exit = state["lots_held"]
                state["state"] = "INVALIDATED"
                state["lots_held"] = 0
                state["next_action"] = "Invalidated: Closed above VWAP."
                await self._emit_signal(candle.instrument, "EXIT_ALL", state, lots_before_exit, state["current_sl"], state["next_action"])
                return

            # Dynamic Reversal / Tier 2 logic
            if state["state"] == "ENTRY_TIER_1":
                # Check for strong reversal candle
                candle_body = abs(candle.close - candle.open)
                candle_range = candle.high - candle.low
                is_strong_reversal = False

                if candle_range > 0 and (candle_body / candle_range) > 0.6:
                    if is_bullish and candle.close > candle.open:
                        is_strong_reversal = True
                    elif not is_bullish and candle.close < candle.open:
                        is_strong_reversal = True

                if is_strong_reversal:
                    # Immediate Tier 2 add
                    new_sl = state["last_vwap"] - self.stop_buffer_points if is_bullish else state["last_vwap"] + self.stop_buffer_points
                    await self._execute_entry(candle.instrument, state, "ENTRY_TIER_2", self.tier_2_lots, candle.close, new_sl)
                    state["next_action"] = "Added Tier 2 on strong reversal."
                else:
                    # Normal pullback to SuperTrend
                    if is_bullish and candle.low <= state["supertrend"] + self.stop_buffer_points:
                        await self._execute_entry(candle.instrument, state, "ENTRY_TIER_2", self.tier_2_lots, candle.close, candle.low - self.stop_buffer_points)
                        state["next_action"] = "Added Tier 2 on SuperTrend pullback."
                    elif not is_bullish and candle.high >= state["supertrend"] - self.stop_buffer_points:
                        await self._execute_entry(candle.instrument, state, "ENTRY_TIER_2", self.tier_2_lots, candle.close, candle.high + self.stop_buffer_points)
                        state["next_action"] = "Added Tier 2 on SuperTrend pullback."

            # Tier 3 Logic
            elif state["state"] == "ENTRY_TIER_2":
                if is_bullish and candle.low <= state["current_day_low"] + self.stop_buffer_points:
                    await self._execute_entry(candle.instrument, state, "ENTRY_TIER_3", self.tier_3_lots, candle.close, state["current_day_low"] - self.stop_buffer_points)
                    state["next_action"] = "Added Tier 3 at Day Low."
                elif not is_bullish and candle.high >= state["current_day_high"] - self.stop_buffer_points:
                    await self._execute_entry(candle.instrument, state, "ENTRY_TIER_3", self.tier_3_lots, candle.close, state["current_day_high"] + self.stop_buffer_points)
                    state["next_action"] = "Added Tier 3 at Day High."

            # Trailing Stop Logic (Candle by Candle)
            if state["state"] in ["BREAK_EVEN", "TRAILING", "PROFIT_PROTECTION"]:
                if is_bullish:
                    new_stop = candle.low - self.stop_buffer_points
                    if new_stop > state["current_sl"]:
                        state["current_sl"] = new_stop
                        state["state"] = "TRAILING"
                        state["next_action"] = "Trailed stop upward."
                        await self._emit_signal(candle.instrument, "TRAIL_SL", state, state["lots_held"], state["current_sl"], state["next_action"])
                elif not is_bullish:
                    new_stop = candle.high + self.stop_buffer_points
                    if new_stop < state["current_sl"] or state["current_sl"] == 0.0:
                        state["current_sl"] = new_stop
                        state["state"] = "TRAILING"
                        state["next_action"] = "Trailed stop downward."
                        await self._emit_signal(candle.instrument, "TRAIL_SL", state, state["lots_held"], state["current_sl"], state["next_action"])

    async def _execute_entry(self, instrument: str, state: Dict[str, Any], tier: str, lots: int, price: float, stop_loss: float):
        state["state"] = tier

        # Calculate new average
        total_lots = state["lots_held"] + lots
        total_value = (state["avg_entry_price"] * state["lots_held"]) + (price * lots)
        state["avg_entry_price"] = total_value / total_lots
        state["lots_held"] = total_lots

        if tier == "ENTRY_TIER_1":
            state["entry_tier_1_price"] = price
            # Only count as a trade on the first tier
            self.daily_trades_count += 1
            state["daily_trades_count"] = self.daily_trades_count

        state["current_sl"] = stop_loss
        state["next_action"] = f"Entered {tier}. Managing position."

        action = "BUY_CE" if state["position_direction"] == 1 else "BUY_PE"
        await self._emit_signal(instrument, tier if tier != "ENTRY_TIER_1" else action, state, lots, stop_loss, state["next_action"])

    async def _emit_signal(self, instrument: str, action: str, state: Dict[str, Any], lots: int, stop_loss: float, reason: str):
        underlying = instrument.replace(" FUT", "").strip() or "NIFTY"
        option_type = "CE" if state["position_direction"] == 1 else "PE"
        direction_label = "BULLISH" if option_type == "CE" else "BEARISH"
        ref_price = state["avg_entry_price"] or state["last_vwap"]
        selected = StrikeSelectionService.select_strike(underlying, ref_price, direction_label)
        resolved_instrument = f"{underlying}{selected.strike_price}{selected.option_type}"

        signal = {
            "signal_id": f"SIG_{self.strategy_id}_{datetime.now().timestamp()}",
            "strategy_id": self.strategy_id,
            "strategy_name": "Intraday Trend Scalper",
            "instrument": resolved_instrument,
            "action": action,
            "timestamp": datetime.now(),
            "direction": "CALL" if option_type == "CE" else "PUT",
            # No real confidence score is computed (rule confluence, not a
            # probability model) — fixed placeholder so OpportunityEngine
            # can convert the signal at all.
            "confidence": 80.0,
            "evidence": reason,
            "lots": lots,
            "stop_loss": stop_loss,
        }
        await event_bus.publish("STRATEGY_SIGNAL", signal)

    async def _handle_market_tick(self, tick: Tick):
        if tick.instrument not in self.positions:
            return

        state = self.positions[tick.instrument]

        if state["state"] in ["ENTRY_TIER_1", "ENTRY_TIER_2", "ENTRY_TIER_3", "PROFIT_PROTECTION", "BREAK_EVEN", "TRAILING"]:
            is_bullish = state["position_direction"] == 1

            # Check Hard Stop Hit
            if is_bullish and tick.price <= state["current_sl"]:
                lots_before_exit = state["lots_held"]
                state["state"] = "EXITED"
                state["lots_held"] = 0
                state["next_action"] = "Stop loss hit."
                await self._emit_signal(tick.instrument, "EXIT_ALL", state, lots_before_exit, state["current_sl"], state["next_action"])
                return
            elif not is_bullish and tick.price >= state["current_sl"] and state["current_sl"] > 0:
                lots_before_exit = state["lots_held"]
                state["state"] = "EXITED"
                state["lots_held"] = 0
                state["next_action"] = "Stop loss hit."
                await self._emit_signal(tick.instrument, "EXIT_ALL", state, lots_before_exit, state["current_sl"], state["next_action"])
                return

            # Check Partial Profit
            if not state["partial_profit_taken"]:
                profit = tick.price - state["avg_entry_price"] if is_bullish else state["avg_entry_price"] - tick.price
                if profit >= self.partial_profit_points:
                    state["partial_profit_taken"] = True
                    exit_lots = state["lots_held"] - max(1, state["lots_held"] // 2)
                    state["lots_held"] = max(1, state["lots_held"] // 2)
                    state["state"] = "PROFIT_PROTECTION"

                    # Move to Break Even
                    if is_bullish:
                        if state["avg_entry_price"] > state["current_sl"]:
                            state["current_sl"] = state["avg_entry_price"]
                            state["state"] = "BREAK_EVEN"
                    else:
                        if state["avg_entry_price"] < state["current_sl"] or state["current_sl"] == 0:
                            state["current_sl"] = state["avg_entry_price"]
                            state["state"] = "BREAK_EVEN"

                    state["next_action"] = "Partial profit taken. Stop at Break Even."
                    await self._emit_signal(tick.instrument, "EXIT_PARTIAL", state, exit_lots, state["current_sl"], state["next_action"])

    async def _handle_trending_oi(self, data: Dict[str, Any]):
        if data.get("view") != "spot_trending_oi":
            return

        row = data.get("row", {})
        underlying = data.get("underlying", "NIFTY")
        instrument = f"{underlying} FUT" # Map to FUT since our state works off Futures

        state = self._get_instrument_state(instrument)

        diff_oi = row.get("differenceOi", 0.0)
        state["diff_oi"] = diff_oi

        # Determine conviction based on current OI difference
        if diff_oi >= self.bullish_oi_difference_threshold:
            state["bullish_oi_confirmed"] = True
            state["bearish_oi_confirmed"] = False
        elif diff_oi <= -self.bullish_oi_difference_threshold:
            state["bearish_oi_confirmed"] = True
            state["bullish_oi_confirmed"] = False
        else:
            state["bullish_oi_confirmed"] = False
            state["bearish_oi_confirmed"] = False

    async def _publish_loop(self):
        while self.running:
            await asyncio.sleep(1) # Publish at 1Hz

            for instrument, state in self.positions.items():
                payload = {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "symbol": instrument,
                    "market_regime": state["state"],
                    "oi_difference": state["diff_oi"],
                    "daily_trades_count": state["daily_trades_count"],
                    "execution_state": {
                        "status": state["state"],
                        "avg_entry": state["avg_entry_price"],
                        "current_sl": state["current_sl"],
                        "quantity": state["lots_held"],
                        "next_action": state["next_action"]
                    }
                }
                # Publish the internal state on its own topic
                await event_bus.publish(self.strategy_id, payload)


intraday_trend_scalper = IntradayTrendScalper()
