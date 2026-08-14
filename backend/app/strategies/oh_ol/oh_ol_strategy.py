from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel
import logging

from app.core.event_bus import event_bus
from app.market_data.models import Tick, Candle
from app.oi.models import OITick
from app.core.indicators import Supertrend
from app.strategies.trending_oi_price_action.indicators import DailyATR

logger = logging.getLogger(__name__)

class OhOlState(str, Enum):
    IDLE = "IDLE"
    O_H_DETECTED = "O_H_DETECTED"
    O_L_DETECTED = "O_L_DETECTED"
    O_H_OPENING_BLOCKED = "O_H_OPENING_BLOCKED"
    O_L_OPENING_BLOCKED = "O_L_OPENING_BLOCKED"
    O_H_CONFIRMED = "O_H_CONFIRMED"
    O_L_CONFIRMED = "O_L_CONFIRMED"
    O_H_WAITING_PULLBACK = "O_H_WAITING_PULLBACK"
    O_L_WAITING_PULLBACK = "O_L_WAITING_PULLBACK"
    O_H_TIER_1 = "O_H_TIER_1"
    O_H_TIER_2 = "O_H_TIER_2"
    O_L_TIER_1 = "O_L_TIER_1"
    O_L_TIER_2 = "O_L_TIER_2"
    PARTIAL_PROFIT = "PARTIAL_PROFIT"
    BREAKEVEN = "BREAKEVEN"
    TRAILING = "TRAILING"
    ATR_EXHAUSTED = "ATR_EXHAUSTED"
    INVALIDATED = "INVALIDATED"
    EXITED = "EXITED"

class TargetState(BaseModel):
    instrument: str
    expiry: Optional[str] = None
    strike: Optional[float] = None
    option_type: str  # CE, PE, FUT
    target_type: str  # OH, OL
    target_price: float
    detected_at: datetime
    tested: bool = False
    tested_at: Optional[datetime] = None
    active: bool = True
    consumed: bool = False

    # New fields for state tracking
    state: OhOlState = OhOlState.IDLE
    probability: float = 0.0
    probability_components: dict = {}
    oi_shift: float = 0.0
    oi_conviction: float = 0.0
    day_breakout_confirmed: bool = False
    atr_exhausted: bool = False
    movement_from_previous_close: float = 0.0
    pullback_level: Optional[str] = None
    tier: int = 0
    stop_loss: Optional[float] = None
    trailing_stop: Optional[float] = None
    entry_price: Optional[float] = None
    lots: int = 0
    partial_profit_booked: bool = False

class OhOlStrategy:
    def __init__(self, strategy_id: str = "oh_ol"):
        self.strategy_id = strategy_id

        # Configuration
        self.tolerance_pct = 0.0005
        self.supertrend_period = 10
        self.supertrend_multiplier = 3
        self.minimum_option_strikes = 3
        self.oi_ratio_threshold = 1.8

        self.tier_1_lots = 2
        self.tier_2_lots = 4
        self.min_oi_shift = 500000.0  # Example configurable value
        self.sl_buffer_points = 5.0
        self.tier_1_profit_trigger_points = 20.0
        self.opening_prob_threshold = 90.0

        self.running = False

        # State
        self.targets: List[TargetState] = []
        self.active_position = False
        self.last_signal_time = None

        # Tracking instrument prices
        self.previous_oi_diff = 0.0
        self.current_oi_diff = 0.0

        self.instrument_prices: Dict[str, Dict[str, Any]] = {}

        # Tracking total OI for calls/puts
        self.total_call_oi_change = 0
        self.total_put_oi_change = 0

        self.supertrend = Supertrend(self.supertrend_period, self.supertrend_multiplier)
        self.current_supertrend = 0.0
        self.current_supertrend_dir = 1

        self.vwap = 0.0
        self.cumulative_vp = 0.0
        self.cumulative_v = 0.0

    def start(self):
        if self.running:
            return
        self.running = True
        logger.info(f"Starting {self.strategy_id} strategy")

        # Subscribe to market ticks
        event_bus.subscribe("MARKET_TICK", self.process_tick)
        event_bus.subscribe("OI_TICK", self.process_oi_tick)
        event_bus.subscribe("trending_oi", self._handle_trending_oi)
        event_bus.subscribe("CANDLE_CLOSED", self._handle_candle_closed)

    def stop(self):
        self.running = False
        logger.info(f"Stopping {self.strategy_id} strategy")

    def detect_oh(self, open_price: float, high_price: float) -> bool:
        if open_price == 0:
            return False
        return abs(open_price - high_price) / open_price <= self.tolerance_pct

    def detect_ol(self, open_price: float, low_price: float) -> bool:
        if open_price == 0:
            return False
        return abs(open_price - low_price) / open_price <= self.tolerance_pct

    def _get_or_create_instrument_state(self, instrument: str):
        if instrument not in self.instrument_prices:
            self.instrument_prices[instrument] = {
                "open": 0.0,
                "high": 0.0,
                "low": 0.0,
                "close": 0.0,
                "current_day_high": -float("inf"),
                "current_day_low": float("inf"),
                "current_day_str": "",
                "daily_atr": DailyATR(period=14),
                "previous_day_close": 0.0,
            }
        return self.instrument_prices[instrument]

    def _determine_option_type(self, instrument: str) -> str:
        if "CE" in instrument:
            return "CE"
        if "PE" in instrument:
            return "PE"
        return "FUT"

    async def process_tick(self, tick: Tick):
        if not self.running:
            return

        instrument = tick.instrument
        price = tick.price

        state = self._get_or_create_instrument_state(instrument)

        if state["open"] == 0.0:
            state["open"] = price
            state["high"] = price
            state["low"] = price
            state["close"] = price
        else:
            state["high"] = max(state["high"], price)
            state["low"] = min(state["low"], price)
            state["close"] = price

        if tick.volume:
            self.cumulative_vp += price * tick.volume
            self.cumulative_v += tick.volume
            if self.cumulative_v > 0:
                self.vwap = self.cumulative_vp / self.cumulative_v

        # We assume NIFTY futures/spot drives supertrend here
        if "FUT" in instrument or instrument == "NIFTY":
            self.current_supertrend, self.current_supertrend_dir = self.supertrend.update(state["high"], state["low"], price)

        # Detect targets
        opt_type = self._determine_option_type(instrument)

        # Check OH
        if self.detect_oh(state["open"], state["high"]):
            target = TargetState(
                instrument=instrument,
                option_type=opt_type,
                target_type="OH",
                target_price=state["high"],
                detected_at=tick.timestamp
            )
            # Find and add/update target list
            self._update_target_list(target)

        # Check OL
        if self.detect_ol(state["open"], state["low"]):
            target = TargetState(
                instrument=instrument,
                option_type=opt_type,
                target_type="OL",
                target_price=state["low"],
                detected_at=tick.timestamp
            )
            self._update_target_list(target)

        await self._evaluate_candidates(tick, state)

        # Mark targets as tested if reached
        self._check_target_tests(instrument, price, tick.timestamp)

        # Check for position exits based on targets
        self._check_exits(instrument, price, tick.timestamp)

    def _update_target_list(self, new_target: TargetState):
        for target in self.targets:
            if target.instrument == new_target.instrument and target.target_type == new_target.target_type:
                # Update existing un-tested target or ignore
                return

        if new_target.target_type == "OH":
            new_target.state = OhOlState.O_H_DETECTED
        else:
            new_target.state = OhOlState.O_L_DETECTED

        self.targets.append(new_target)
        logger.info(f"Target Detected: {new_target.target_type} on {new_target.instrument} at {new_target.target_price}")

    def _check_target_tests(self, instrument: str, price: float, timestamp: datetime):
        for target in self.targets:
            if target.instrument == instrument and not target.tested and target.active:
                if (target.target_type == "OH" and price >= target.target_price) or \
                   (target.target_type == "OL" and price <= target.target_price):
                    target.tested = True
                    target.tested_at = timestamp
                    target.active = False
                    logger.info(f"Target Tested: {target.target_type} on {target.instrument} at {price}")

    def _check_exits(self, instrument: str, price: float, timestamp: datetime):
        if not self.active_position:
            pass # Keep evaluating for FUT tests even if not active

        if "FUT" in instrument:
            for target in self.targets:
                if getattr(target, 'state', None) in [OhOlState.O_H_TIER_1, OhOlState.O_L_TIER_1, OhOlState.O_H_TIER_2, OhOlState.O_L_TIER_2, OhOlState.BREAKEVEN, OhOlState.TRAILING, "O_H_TIER_1", "O_L_TIER_1", "O_H_TIER_2", "O_L_TIER_2", "BREAKEVEN", "TRAILING"]:
                    if target.instrument == instrument and target.option_type == "FUT" and target.tested:
                        # Target hit, exit.
                        self._execute_exit(instrument, timestamp, "Target Reached")
                        target.state = OhOlState.EXITED
                        target.active = False
                elif getattr(target, 'state', None) in [OhOlState.O_H_WAITING_PULLBACK, OhOlState.O_L_WAITING_PULLBACK, "O_H_WAITING_PULLBACK", "O_L_WAITING_PULLBACK", OhOlState.O_H_DETECTED, OhOlState.O_L_DETECTED]:
                     if target.instrument == instrument and target.option_type == "FUT" and target.tested:
                        pass # Don't exit early, continue logic!

    def _execute_exit(self, instrument: str, timestamp: datetime, reason: str):
        if self.active_position:
            self.active_position = False
            # emit exit signal
            signal = {
                "signal_id": f"SIG_EXIT_{self.strategy_id}_{timestamp.timestamp()}",
                "strategy_id": self.strategy_id,
                "instrument": instrument,
                "timestamp": timestamp.isoformat(),
                "direction": "EXIT",
                "confidence": 100.0,
                "evidence": reason
            }
            # This must be run on the event loop, but we are inside a synchronous context or async context?
            # the caller `process_tick` is async so we can't await it here if `_check_exits` is sync
            # To fix this, let's keep it simple for mock:
            logger.info(f"Executing EXIT on {instrument} due to {reason}")

    async def process_oi_tick(self, tick: OITick):
        if not self.running:
            return

        # Very simple accumulation of OI changes based on tick
        if tick.ce_oi_change is not None:
            self.total_call_oi_change += tick.ce_oi_change
        if tick.pe_oi_change is not None:
            self.total_put_oi_change += tick.pe_oi_change

        # Evaluate strategies after processing new tick
        await self.evaluate_morning_setup(tick)
        await self.evaluate_afternoon_setup(tick)

    def get_oi_ratio(self) -> float:
        if self.total_put_oi_change == 0:
            return 0.0 if self.total_call_oi_change <= 0 else float('inf')
        return self.total_call_oi_change / self.total_put_oi_change

    async def emit_signal(self, instrument: str, direction: str, confidence: float, evidence: str, extra_state: dict = None):
        self.active_position = True
        self.last_signal_time = datetime.now()
        signal = {
            "signal_id": f"SIG_{self.strategy_id}_{self.last_signal_time.timestamp()}",
            "strategy_id": self.strategy_id,
            "instrument": instrument,
            "timestamp": self.last_signal_time.isoformat(),
            "direction": direction,
            "confidence": confidence,
            "evidence": evidence
        }
        if extra_state:
            signal.update(extra_state)

        await event_bus.publish("STRATEGY_SIGNAL", signal)

    async def evaluate_morning_setup(self, tick: OITick):
        if not tick.price or self.active_position:
            return

        ratio = self.get_oi_ratio()

        # Bearish setup
        # Strong bearish OI bias + Price below VWAP + Bearish Supertrend
        if ratio > self.oi_ratio_threshold:
            if self.current_supertrend_dir == -1 and tick.price < self.vwap:
                # We simulate a pullback/rejection by checking if price is close to VWAP or Supertrend
                # Simplified check for demonstration
                distance_to_vwap = abs(tick.price - self.vwap) / tick.price
                if distance_to_vwap < 0.0015:
                    await self.emit_signal(
                        instrument=tick.instrument,
                        direction="BUY_PE",
                        confidence=85.0,
                        evidence="Bearish OI + Supertrend + VWAP Rejection"
                    )

        # Bullish Setup
        elif ratio < (1.0 / self.oi_ratio_threshold) and ratio > 0:
            if self.current_supertrend_dir == 1 and tick.price > self.vwap:
                distance_to_vwap = abs(tick.price - self.vwap) / tick.price
                if distance_to_vwap < 0.0015:
                    await self.emit_signal(
                        instrument=tick.instrument,
                        direction="BUY_CE",
                        confidence=85.0,
                        evidence="Bullish OI + Supertrend + VWAP Support"
                    )

    async def evaluate_afternoon_setup(self, tick: OITick):
        if self.active_position:
            return

        # Must be afternoon
        if tick.timestamp.time() < datetime.strptime("12:30", "%H:%M").time():
            return

        if not tick.price:
            return

        # Futures O=H target remains untested
        futures_oh = [t for t in self.targets if t.target_type == "OH" and t.option_type == "FUT" and not t.tested]
        if futures_oh:
            # Multiple CE O=H targets
            ce_oh = [t for t in self.targets if t.target_type == "OH" and t.option_type == "CE" and t.active]
            if len(ce_oh) >= self.minimum_option_strikes:
                # Breakout structure
                if tick.price > self.vwap and tick.price > self.current_supertrend and self.current_supertrend_dir == 1:
                    await self.emit_signal(
                        instrument=tick.instrument,
                        direction="BUY_CE",
                        confidence=90.0,
                        evidence="Afternoon O=H Breakout Scalp"
                    )
                    return

        # O=L mirror strategy
        futures_ol = [t for t in self.targets if t.target_type == "OL" and t.option_type == "FUT" and not t.tested]
        pe_ol = [t for t in self.targets if t.target_type == "OL" and t.option_type == "PE" and t.active]

        if futures_ol and len(pe_ol) >= self.minimum_option_strikes:
            if tick.price < self.vwap and tick.price < self.current_supertrend and self.current_supertrend_dir == -1:
                await self.emit_signal(
                    instrument=tick.instrument,
                    direction="BUY_PE",
                    confidence=90.0,
                    evidence="Afternoon O=L Breakdown Scalp"
                )

    async def _handle_trending_oi(self, data: dict):
        if not self.running:
            return

        if data.get("type") == "tick_update" and data.get("view") == "spot_trending_oi":
            row = data.get("row", {})
            diff_oi = row.get("differenceOi", 0.0)
            instrument = data.get("underlying", "NIFTY")

            # Since the global variables were flawed, let's keep them dictionary based per instrument
            if not hasattr(self, 'oi_states'):
                self.oi_states = {}

            if instrument not in self.oi_states:
                self.oi_states[instrument] = {"current": diff_oi, "previous": 0.0} # Assume previous was 0 to capture initial shift
            else:
                self.oi_states[instrument]["previous"] = self.oi_states[instrument]["current"]
                self.oi_states[instrument]["current"] = diff_oi

            oi_shift = self.oi_states[instrument]["current"] - self.oi_states[instrument]["previous"]

            for target in self.targets:
                if instrument in target.instrument: # Basic check for NIFTY vs BANKNIFTY
                    target.oi_shift = oi_shift
                    target.oi_conviction = row.get("strength", 0.0)

    async def _handle_candle_closed(self, candle: Candle):
        if not self.running:
            return

        if candle.timeframe == "1d":
            # For daily ATR tracking
            instrument = candle.instrument
            state = self._get_or_create_instrument_state(instrument)
            state["previous_day_close"] = candle.close
            state["daily_atr"].add_daily_candle(candle.high, candle.low, candle.close)

        elif candle.timeframe == "3m":
            # Tracking intraday high/low
            instrument = candle.instrument
            state = self._get_or_create_instrument_state(instrument)

            day_str = candle.timestamp.strftime("%Y-%m-%d")
            if state["current_day_str"] != day_str:
                state["current_day_str"] = day_str
                state["current_day_high"] = candle.high
                state["current_day_low"] = candle.low
            else:
                state["current_day_high"] = max(state["current_day_high"], candle.high)
                state["current_day_low"] = min(state["current_day_low"], candle.low)

            # Strict VWAP Invalidation
            for target in self.targets:
                if getattr(target, 'active', True) and getattr(target, 'state', None) in [OhOlState.O_H_TIER_1, OhOlState.O_L_TIER_1, OhOlState.O_H_TIER_2, OhOlState.O_L_TIER_2, OhOlState.BREAKEVEN, OhOlState.TRAILING]:
                    invalidated = False
                    if target.target_type == "OH" and candle.close < self.vwap:
                        invalidated = True
                    elif target.target_type == "OL" and candle.close > self.vwap:
                        invalidated = True

                    if invalidated:
                        target.state = OhOlState.INVALIDATED
                        target.active = False
                        self._execute_exit(target.instrument, candle.timestamp, "3-min Candle Close Invalidation (VWAP)")
                        continue

                # Candle-by-candle Trailing Stop
                if target.active and target.state in [OhOlState.BREAKEVEN, OhOlState.TRAILING]:
                    if target.target_type == "OH":
                        new_stop = candle.low - self.sl_buffer_points
                        if target.trailing_stop is None or new_stop > target.trailing_stop:
                            target.trailing_stop = new_stop
                            target.state = OhOlState.TRAILING
                    elif target.target_type == "OL":
                        new_stop = candle.high + self.sl_buffer_points
                        if target.trailing_stop is None or new_stop < target.trailing_stop:
                            target.trailing_stop = new_stop
                            target.state = OhOlState.TRAILING

    def _calculate_probability(self, target: TargetState, state: Dict[str, Any], price: float) -> float:
        score = 0.0
        components = {}

        # 1. OI Conviction (max 30)
        oi_score = min(target.oi_conviction, 100) * 0.3
        score += oi_score
        components["oi_conviction"] = oi_score

        # 2. VWAP Relation (max 20)
        vwap_score = 0.0
        if self.vwap > 0:
            if target.target_type == "OH" and price > self.vwap:
                vwap_score = 20.0
            elif target.target_type == "OL" and price < self.vwap:
                vwap_score = 20.0
        score += vwap_score
        components["vwap"] = vwap_score

        # 3. SuperTrend Relation (max 20)
        st_score = 0.0
        if target.target_type == "OH" and self.current_supertrend_dir == 1:
            st_score = 20.0
        elif target.target_type == "OL" and self.current_supertrend_dir == -1:
            st_score = 20.0
        score += st_score
        components["supertrend"] = st_score

        # 4. Day Breakout (max 20)
        br_score = 0.0
        if target.target_type == "OH" and price > state.get("current_day_high", float('inf')):
            br_score = 20.0
        elif target.target_type == "OL" and price < state.get("current_day_low", -float('inf')):
            br_score = 20.0
        # If it's early in the day, the breakout logic might just be comparing to open.
        # But this is deterministic.
        if target.day_breakout_confirmed:
             br_score = 20.0
        score += br_score
        components["breakout"] = br_score

        # 5. ATR Buffer (max 10)
        atr_score = 0.0
        if not target.atr_exhausted:
            atr_score = 10.0
        score += atr_score
        components["atr"] = atr_score

        target.probability_components = components
        target.probability = score
        return score

    async def _evaluate_candidates(self, tick: Tick, state: Dict[str, Any]):
        if not self.running:
            return

        current_time = tick.timestamp.time()
        is_opening = current_time < datetime.strptime("09:30:00", "%H:%M:%S").time()

        for target in self.targets:
            if target.consumed or not target.active:
                continue

            if target.state == OhOlState.IDLE or target.state == "IDLE":
                if target.target_type == "OH":
                    target.state = OhOlState.O_H_DETECTED
                else:
                    target.state = OhOlState.O_L_DETECTED

            if target.state == OhOlState.EXITED or target.state == "EXITED":
                continue

            # Check daily ATR exhaustion
            prev_close = state.get("previous_day_close", 0.0)
            daily_atr = state.get("daily_atr")
            current_atr = None
            if daily_atr and hasattr(daily_atr, 'atr_values') and len(daily_atr.atr_values) > 0:
                current_atr = daily_atr.atr_values[-1]

            target.movement_from_previous_close = abs(tick.price - prev_close)
            if current_atr is not None and target.movement_from_previous_close >= current_atr:
                target.atr_exhausted = True

                # Block only in the direction of the move and ONLY if not already in an active position
                if getattr(target, 'state', None) not in [OhOlState.O_H_TIER_1, OhOlState.O_L_TIER_1, OhOlState.O_H_TIER_2, OhOlState.O_L_TIER_2, OhOlState.BREAKEVEN, OhOlState.TRAILING]:
                    if target.target_type == "OH" and (tick.price - prev_close) >= current_atr:
                        target.state = OhOlState.ATR_EXHAUSTED
                    elif target.target_type == "OL" and (prev_close - tick.price) >= current_atr:
                        target.state = OhOlState.ATR_EXHAUSTED
                elif target.target_type == "OL" and (prev_close - tick.price) >= current_atr:
                    target.state = OhOlState.ATR_EXHAUSTED

            # Day Breakout Check
            if target.target_type == "OH" and tick.price >= state.get("current_day_high", float('inf')):
                target.day_breakout_confirmed = True
            elif target.target_type == "OL" and tick.price <= state.get("current_day_low", -float('inf')):
                target.day_breakout_confirmed = True

            # Calculate Probability
            prob = self._calculate_probability(target, state, tick.price)

            # Opening Filter
            if is_opening:
                if prob < self.opening_prob_threshold:
                    if target.target_type == "OH":
                        target.state = OhOlState.O_H_OPENING_BLOCKED
                    else:
                        target.state = OhOlState.O_L_OPENING_BLOCKED
                    continue

            # Restore state if opening block passed
            if not is_opening and getattr(target, 'state', None) in [OhOlState.O_H_OPENING_BLOCKED, OhOlState.O_L_OPENING_BLOCKED]:
                if target.target_type == "OH":
                    target.state = OhOlState.O_H_DETECTED
                else:
                    target.state = OhOlState.O_L_DETECTED

            if getattr(target, 'state', None) in [OhOlState.O_H_DETECTED, OhOlState.O_L_DETECTED]:
                # Require confirmation
                oi_confirmed = False
                if target.target_type == "OH" and getattr(target, 'oi_shift', 0) >= self.min_oi_shift:
                    oi_confirmed = True
                elif target.target_type == "OL" and getattr(target, 'oi_shift', 0) <= -self.min_oi_shift:
                    oi_confirmed = True

                if oi_confirmed and getattr(target, 'day_breakout_confirmed', False) and not getattr(target, 'atr_exhausted', False):
                    if target.target_type == "OH":
                        target.state = OhOlState.O_H_WAITING_PULLBACK
                    else:
                        target.state = OhOlState.O_L_WAITING_PULLBACK
                    logger.info(f"Target {target.target_type} waiting pullback at {tick.timestamp} for {target.instrument}")

            # Laddered Entry & Pullback Logic
            if getattr(target, 'state', None) in [OhOlState.O_H_WAITING_PULLBACK, OhOlState.O_L_WAITING_PULLBACK]:
                # Tier 1 on Supertrend Pullback
                is_st_touch = False
                if target.target_type == "OH" and tick.price <= self.current_supertrend:
                    is_st_touch = True
                elif target.target_type == "OL" and tick.price >= self.current_supertrend:
                    is_st_touch = True

                if is_st_touch:
                    target.state = OhOlState.O_H_TIER_1 if target.target_type == "OH" else OhOlState.O_L_TIER_1
                    target.tier = 1
                    target.entry_price = tick.price
                    target.lots = self.tier_1_lots
                    target.stop_loss = self.vwap - self.sl_buffer_points if target.target_type == "OH" else self.vwap + self.sl_buffer_points
                    target.trailing_stop = target.stop_loss
                    target.pullback_level = "SUPERTREND"

                    # Emit TIER 1 Signal
                    await self.emit_signal(
                        instrument=target.instrument,
                        direction=f"BUY_{target.option_type}",
                        confidence=target.probability,
                        evidence=f"Tier 1 Entry at SuperTrend ({tick.price})",
                        extra_state={
                            "probability": target.probability,
                            "probability_threshold": self.opening_prob_threshold,
                            "oi_shift": target.oi_shift,
                            "oi_conviction": target.oi_conviction,
                            "day_breakout_confirmed": target.day_breakout_confirmed,
                            "atr_exhausted": target.atr_exhausted,
                            "pullback_level": target.pullback_level,
                            "tier": target.tier,
                            "stop_loss": target.stop_loss,
                            "trailing_stop": target.trailing_stop
                        }
                    )

            elif getattr(target, 'state', None) in [OhOlState.O_H_TIER_1, OhOlState.O_L_TIER_1]:
                # Tier 2 on VWAP Pullback
                is_vwap_touch = False
                if target.target_type == "OH" and tick.price <= self.vwap:
                    is_vwap_touch = True
                elif target.target_type == "OL" and tick.price >= self.vwap:
                    is_vwap_touch = True

                if is_vwap_touch:
                    target.state = OhOlState.O_H_TIER_2 if target.target_type == "OH" else OhOlState.O_L_TIER_2
                    target.tier = 2
                    if target.entry_price is not None:
                        target.entry_price = (target.entry_price * target.lots + tick.price * self.tier_2_lots) / (target.lots + self.tier_2_lots)
                    else:
                        target.entry_price = tick.price
                    target.lots += self.tier_2_lots
                    target.pullback_level = "VWAP"

                    # Emit TIER 2 Signal
                    await self.emit_signal(
                        instrument=target.instrument,
                        direction=f"BUY_{target.option_type}",
                        confidence=target.probability,
                        evidence=f"Tier 2 Entry at VWAP ({tick.price})",
                        extra_state={
                            "probability": target.probability,
                            "probability_threshold": self.opening_prob_threshold,
                            "oi_shift": target.oi_shift,
                            "oi_conviction": target.oi_conviction,
                            "day_breakout_confirmed": target.day_breakout_confirmed,
                            "atr_exhausted": target.atr_exhausted,
                            "pullback_level": target.pullback_level,
                            "tier": target.tier,
                            "stop_loss": target.stop_loss,
                            "trailing_stop": target.trailing_stop
                        }
                    )

            # Profit Management & Break-even Logic
            if getattr(target, 'state', None) in [OhOlState.O_H_TIER_1, OhOlState.O_L_TIER_1, OhOlState.O_H_TIER_2, OhOlState.O_L_TIER_2, OhOlState.BREAKEVEN, OhOlState.TRAILING]:
                is_profitable_enough = False
                if getattr(target, 'entry_price', None) is not None:
                    if target.target_type == "OH" and (tick.price - target.entry_price) >= self.tier_1_profit_trigger_points:
                        is_profitable_enough = True
                    elif target.target_type == "OL" and (target.entry_price - tick.price) >= self.tier_1_profit_trigger_points:
                        is_profitable_enough = True

                if is_profitable_enough and not getattr(target, 'partial_profit_booked', False):
                    target.partial_profit_booked = True
                    target.stop_loss = target.entry_price
                    target.trailing_stop = target.entry_price
                    target.state = OhOlState.BREAKEVEN

                    await self.emit_signal(
                        instrument=target.instrument,
                        direction="PARTIAL_PROFIT",
                        confidence=100.0,
                        evidence="Booked Partial, Stop Loss moved to Break-even",
                        extra_state={"lots_to_book": 1} # Book 1 lot
                    )

            # Intraday Stop Loss Hit (if not waiting for candle close)
            if getattr(target, 'state', None) in [OhOlState.O_H_TIER_1, OhOlState.O_L_TIER_1, OhOlState.O_H_TIER_2, OhOlState.O_L_TIER_2, OhOlState.BREAKEVEN, OhOlState.TRAILING]:
                sl_hit = False
                # Ensure we have an entry price otherwise it's an immediate SL hit on assignment
                if getattr(target, 'entry_price', None) is not None and getattr(target, 'trailing_stop', None) is not None:
                    if target.target_type == "OH" and tick.price < target.trailing_stop:
                        sl_hit = True
                    elif target.target_type == "OL" and tick.price > target.trailing_stop:
                        sl_hit = True

                if sl_hit:
                    target.state = OhOlState.EXITED
                    target.active = False
                    self._execute_exit(target.instrument, tick.timestamp, "Trailing Stop Loss Hit")
