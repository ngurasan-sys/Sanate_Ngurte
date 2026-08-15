import logging
from datetime import datetime
from typing import Dict, Any, Optional
import pytz

from backend.app.core.event_bus import event_bus
from backend.app.market_data.models import Tick, Candle
from .models import StrategyConfig, PositionState, StrategySignal
from .indicators import IndicatorEngine
from .strike_selection import StrikeSelectionService

logger = logging.getLogger(__name__)

IST = pytz.timezone('Asia/Kolkata')

class GapOpeningEngine:
    def __init__(self, config: Optional[StrategyConfig] = None):
        self.config = config or StrategyConfig()
        self.indicators = IndicatorEngine(
            atr_period=self.config.atr_period,
            supertrend_period=self.config.supertrend_period,
            supertrend_multiplier=self.config.supertrend_multiplier
        )
        self.state: Dict[str, PositionState] = {}

        # Market context per instrument
        self.context: Dict[str, Dict[str, Any]] = {}

        # Daily Tracking
        self.day_high: Dict[str, float] = {}
        self.day_low: Dict[str, float] = {}
        self.today_open: Dict[str, float] = {}
        self.previous_close: Dict[str, float] = {}
        self.opening_candle_high: Dict[str, float] = {}
        self.vwap: Dict[str, float] = {}

        # OI Data
        self.diff_oi_pct: Dict[str, float] = {}
        self.net_pcr: Dict[str, float] = {}
        self.oi_regime: Dict[str, str] = {}

        # VIX Data — no VIX_UPDATE publisher exists yet, so this stays
        # unavailable (None) rather than defaulting to a fake 0.0 reading,
        # which would misrepresent "no data" as "VIX flat".
        self.vix_1h_change_pct: Optional[float] = None
        self.vix_override: bool = False
        self.current_vix: float = 0.0
        self._vix_data_received: bool = False

    def start(self):
        event_bus.subscribe("MARKET_TICK", self.handle_tick)
        event_bus.subscribe("CANDLE_CLOSED", self.handle_candle)
        event_bus.subscribe("trending_oi", self.handle_trending_oi)
        event_bus.subscribe("VIX_UPDATE", self.handle_vix)
        logger.info("Gap Opening Strategies Engine started")

    def stop(self):
        # event_bus has no per-callback unsubscribe; subscriptions are
        # cleaned up implicitly when event_bus.stop() cancels all worker
        # tasks during app shutdown. Nothing else to release here.
        logger.info("Gap Opening Strategies Engine stopped")

    def _get_time_ist(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return IST.localize(dt)
        return dt.astimezone(IST)

    def _parse_time(self, t_str: str) -> tuple:
        h, m = map(int, t_str.split(':'))
        return h, m

    def _is_discovery_phase(self, dt: datetime) -> bool:
        ist_dt = self._get_time_ist(dt)
        oh, om = self._parse_time(self.config.opening_time)
        eh, em = self._parse_time(self.config.entry_start_time)

        start_time = ist_dt.replace(hour=oh, minute=om, second=0, microsecond=0)
        end_time = ist_dt.replace(hour=eh, minute=em, second=0, microsecond=0)

        return start_time <= ist_dt < end_time

    def _is_market_open(self, dt: datetime) -> bool:
        ist_dt = self._get_time_ist(dt)
        eh, em = self._parse_time(self.config.entry_start_time)
        end_time = ist_dt.replace(hour=eh, minute=em, second=0, microsecond=0)
        return ist_dt >= end_time

    async def handle_tick(self, tick: Tick):
        inst = tick.instrument
        price = tick.price
        dt = tick.timestamp

        if inst not in self.context:
            self.context[inst] = {"last_price": price}

        prev_price = self.context[inst].get("last_price", price)
        self.context[inst]["last_price"] = price

        # Track High / Low
        if inst not in self.day_high:
            self.day_high[inst] = price
            self.day_low[inst] = price
            self.today_open[inst] = price
        else:
            self.day_high[inst] = max(self.day_high[inst], price)
            self.day_low[inst] = min(self.day_low[inst], price)

        state = self.state.setdefault(inst, PositionState())

        # Guard: State management
        if self._is_discovery_phase(dt):
            state.position_state = "WAITING_FOR_DISCOVERY"
        elif state.position_state == "WAITING_FOR_DISCOVERY":
            state.position_state = "DISCOVERY_COMPLETE"

        # Position Management / Stop breach
        if state.in_position:
            await self._check_stop_breach(inst, price, dt)

    async def handle_candle(self, candle: Candle):
        inst = candle.instrument
        dt = candle.timestamp
        close = candle.close

        # Track opening candle high
        if self._is_discovery_phase(dt) and inst not in self.opening_candle_high:
            self.opening_candle_high[inst] = candle.high
        elif inst not in self.opening_candle_high:
             self.opening_candle_high[inst] = candle.high

        if candle.vwap is not None:
            self.vwap[inst] = candle.vwap

        # Update indicators
        self.indicators.update_candle(inst, candle.high, candle.low, close)

        state = self.state.setdefault(inst, PositionState())

        if self._is_discovery_phase(dt) or not self._is_market_open(dt):
            return

        if not state.in_position:
            await self._evaluate_setup(inst, close, dt)
        else:
            await self._evaluate_position_management(inst, candle)

    async def _evaluate_setup(self, inst: str, price: float, dt: datetime):
        state = self.state[inst]

        regime = self.oi_regime.get(inst, "CHOP")
        diff_pct = self.diff_oi_pct.get(inst, 0.0)
        st = self.indicators.get_supertrend(inst)
        atr = self.indicators.get_atr(inst)
        vwap = self.vwap.get(inst, 0.0)
        day_high = self.day_high.get(inst, price)
        day_low = self.day_low.get(inst, price)
        prev_price = self.context[inst].get("last_price", price)

        # ATR Exhaustion Check
        day_range = day_high - day_low
        atr_exhausted = (day_range >= (self.config.atr_exhaustion_ratio * atr)) if atr > 0 else False

        # Divergence Guard
        bullish_divergence_blocked = (price > prev_price and diff_pct < 0)
        bearish_divergence_blocked = (price < prev_price and diff_pct > 0)

        # Market Mode Selection (Psychological round number)
        is_near_round = False
        step = 100 if "NIFTY" in inst and "BANK" not in inst else (500 if "BANKNIFTY" in inst else 100)
        nearest_round = round(price / step) * step
        if abs(price - nearest_round) <= self.config.round_number_distance:
            is_near_round = True

        mode = "LOW_MOMENTUM_SCALPING" if is_near_round else "TREND_CONTINUATION"

        # Bullish Setup
        if (regime == "BULLISH" and diff_pct >= self.config.oi_bullish_threshold
            and not bullish_divergence_blocked
            and price > st
            and (not atr_exhausted or (atr_exhausted and self.vix_override))):

            # Entry pullback / Tier 1 Check
            if price <= (st + 15): # Pullback towards Supertrend
                await self._execute_entry(inst, price, dt, "BULLISH", mode, st, vwap)

        # Bearish Setup
        elif (regime == "BEARISH" and diff_pct <= self.config.oi_bearish_threshold
              and not bearish_divergence_blocked
              and price < st
              and (not atr_exhausted or (atr_exhausted and self.vix_override))):

            # Entry pullback / Tier 1 Check
            if price >= (st - 15) or price >= (vwap - 15):
                await self._execute_entry(inst, price, dt, "BEARISH", mode, st, vwap)

    async def _execute_entry(self, inst: str, price: float, dt: datetime, direction: str, mode: str, st: float, vwap: float):
        state = self.state[inst]

        # Strike Selection
        option = StrikeSelectionService.select_strike(inst, price, direction)

        lots = self.config.low_momentum_lots if mode == "LOW_MOMENTUM_SCALPING" else self.config.tier_1_lots

        # Initial SL
        if direction == "BULLISH":
            initial_sl = vwap - self.config.bullish_vwap_buffer
        else:
            initial_sl = self.day_high.get(inst, price) + self.config.bearish_stop_buffer

        state.in_position = True
        state.direction = direction
        state.underlying = inst
        state.selected_strike = option.strike_price
        state.instrument_key = option.instrument_key
        state.option_type = option.option_type
        state.expiry = option.expiry
        state.entry_price = price
        state.average_entry_price = price
        state.lots_held = lots
        state.initial_lots = lots
        state.current_sl = initial_sl
        state.highest_favorable_price = price
        state.lowest_favorable_price = price
        state.position_state = "TIER_1_ENTERED"
        state.entry_timestamp = dt

        action = "BUY_CE" if direction == "BULLISH" else "BUY_PE"

        await self._emit_signal(
            inst=inst,
            action=action,
            lots=lots,
            price=price,
            sl=initial_sl,
            mode=mode,
            reason=f"Tier 1 Entry: {direction} pullback in {mode} mode",
            dt=dt
        )

    async def _check_stop_breach(self, inst: str, price: float, dt: datetime):
        state = self.state[inst]
        if not state.in_position:
            return

        if state.direction == "BULLISH":
            state.highest_favorable_price = max(state.highest_favorable_price, price)
            if price <= state.current_sl:
                await self._exit_position(inst, price, dt, "Stop Loss Breach")
                return
        else:
            state.lowest_favorable_price = min(state.lowest_favorable_price, price)
            if price >= state.current_sl:
                await self._exit_position(inst, price, dt, "Stop Loss Breach")
                return

        # Partial Profit Check
        if not state.partial_booked:
            profit = price - state.average_entry_price if state.direction == "BULLISH" else state.average_entry_price - price
            if profit >= self.config.partial_profit_points:
                state.partial_booked = True
                state.current_sl = state.average_entry_price # Break-even
                exit_lots = int(state.lots_held * (self.config.partial_profit_percent / 100))
                state.lots_held -= exit_lots

                await self._emit_signal(
                    inst=inst,
                    action="EXIT_PARTIAL",
                    lots=exit_lots,
                    price=price,
                    sl=state.current_sl,
                    mode="N/A",
                    reason="Partial profit target reached",
                    dt=dt
                )

    async def _evaluate_position_management(self, inst: str, candle: Candle):
        state = self.state[inst]
        if not state.in_position:
            return

        close = candle.close

        step = 100 if "NIFTY" in inst and "BANK" not in inst else (500 if "BANKNIFTY" in inst else 100)
        nearest_round = round(state.entry_price / step) * step
        is_near_round = abs(state.entry_price - nearest_round) <= self.config.round_number_distance
        mode = "LOW_MOMENTUM_SCALPING" if is_near_round else "TREND_CONTINUATION"

        # Tier 2 Check
        if mode == "TREND_CONTINUATION" and not state.tier_2_filled:
            vwap = self.vwap.get(inst, 0.0)
            if state.direction == "BULLISH":
                if (vwap - self.config.tier_2_buffer) <= close <= (vwap + self.config.tier_2_buffer):
                    await self._add_tier_2(inst, close, candle.timestamp)
            else:
                ref_high = max(self.day_high.get(inst, close), self.opening_candle_high.get(inst, close))
                if (ref_high - self.config.tier_2_buffer) <= close <= (ref_high + self.config.tier_2_buffer):
                    await self._add_tier_2(inst, close, candle.timestamp)

        # Candle Trailing SL Logic
        if state.partial_booked:
            # Stage 2 & 3: Expansion & Trailing
            candle_body = abs(candle.close - candle.open)
            is_bullish_candle = candle.close > candle.open

            new_sl = state.current_sl

            if state.direction == "BULLISH":
                # Expansion
                if candle_body >= self.config.expansion_candle_points and is_bullish_candle:
                    new_sl = max(new_sl, candle.low - self.config.trailing_buffer)
                # Normal Trailing
                else:
                    new_sl = max(new_sl, candle.low - self.config.trailing_buffer)
            else:
                # Expansion
                if candle_body >= self.config.expansion_candle_points and not is_bullish_candle:
                    new_sl = min(new_sl, candle.high + self.config.trailing_buffer)
                # Normal Trailing
                else:
                    new_sl = min(new_sl, candle.high + self.config.trailing_buffer)

            if new_sl != state.current_sl:
                # Ensure SL only moves in favorable direction
                if (state.direction == "BULLISH" and new_sl > state.current_sl) or (state.direction == "BEARISH" and new_sl < state.current_sl):
                    state.current_sl = new_sl
                    await self._emit_signal(
                        inst=inst,
                        action="TRAIL_SL",
                        lots=0,
                        price=close,
                        sl=new_sl,
                        mode="N/A",
                        reason="Candle trail",
                        dt=candle.timestamp
                    )

        # EVENT PYRAMID Check
        if mode == "TREND_CONTINUATION" and not state.event_pyramid_used:
            atr = self.indicators.get_atr(inst)
            day_range = self.day_high.get(inst, close) - self.day_low.get(inst, close)
            atr_exhausted = (day_range >= (self.config.atr_exhaustion_ratio * atr)) if atr > 0 else False
            diff_pct = self.diff_oi_pct.get(inst, 0.0)

            regime_valid = (state.direction == "BULLISH" and diff_pct >= self.config.oi_bullish_threshold) or \
                           (state.direction == "BEARISH" and diff_pct <= self.config.oi_bearish_threshold)

            if atr_exhausted and self.vix_override and regime_valid:
                state.event_pyramid_used = True
                await self._emit_signal(
                    inst=inst,
                    action="EVENT_PYRAMID",
                    lots=self.config.tier_2_lots,
                    price=close,
                    sl=state.current_sl,
                    mode=mode,
                    reason="Event Pyramid conditions met",
                    dt=candle.timestamp
                )

    async def _add_tier_2(self, inst: str, price: float, dt: datetime):
        state = self.state[inst]
        state.tier_2_filled = True
        state.position_state = "TIER_2_ENTERED"

        # Calculate new average
        total_cost = (state.average_entry_price * state.lots_held) + (price * self.config.tier_2_lots)
        state.lots_held += self.config.tier_2_lots
        state.average_entry_price = total_cost / state.lots_held

        await self._emit_signal(
            inst=inst,
            action="ADD_TIER_2",
            lots=self.config.tier_2_lots,
            price=price,
            sl=state.current_sl,
            mode="TREND_CONTINUATION",
            reason="Tier 2 zone entered",
            dt=dt
        )

    async def _exit_position(self, inst: str, price: float, dt: datetime, reason: str):
        state = self.state[inst]

        await self._emit_signal(
            inst=inst,
            action="EXIT_ALL",
            lots=state.lots_held,
            price=price,
            sl=state.current_sl,
            mode="N/A",
            reason=reason,
            dt=dt
        )

        # Reset State
        self.state[inst] = PositionState(position_state="EXITED")

    async def _emit_signal(self, inst: str, action: str, lots: int, price: float, sl: float, mode: str, reason: str, dt: datetime):
        state = self.state[inst]
        sig = StrategySignal(
            signal_id=f"GAP_{int(dt.timestamp())}_{inst}",
            strategy_id="gap_opening_strategies",
            strategy_name="Gap Opening Strategies",
            symbol=inst,
            underlying=inst,
            action=action, # type: ignore
            strike_price=state.selected_strike or 0,
            instrument_key=state.instrument_key or "",
            option_type=state.option_type or "",
            expiry=state.expiry or "",
            underlying_price=price,
            option_price=price, # Not strictly modeling option price here
            stop_loss=sl,
            lots=lots,
            regime=self.oi_regime.get(inst, "CHOP"),
            mode=mode,
            diff_oi_pct=self.diff_oi_pct.get(inst, 0.0),
            net_pcr=0.0, # Not tracking currently
            vwap=self.vwap.get(inst, 0.0),
            supertrend=self.indicators.get_supertrend(inst),
            daily_atr=self.indicators.get_atr(inst),
            atr_exhausted=False, # Re-calculate if needed in emit
            vix_1h_change_pct=(self.vix_1h_change_pct if self._vix_data_received else None),
            vix_override=self.vix_override,
            reason=reason,
            timestamp=dt
        )
        await event_bus.publish("STRATEGY_SIGNAL", sig.model_dump())

    async def handle_trending_oi(self, payload: dict):
        # Expected payload from TrendingOIEngine (Spot or Future)
        if payload.get("type") == "tick_update" and "row" in payload:
            row = payload["row"]
            # Check if this is the spot OI payload
            if "differenceOi" in row:
                inst = payload.get("underlying", "NIFTY")
                self.diff_oi_pct[inst] = row.get("directionPercent", 0.0) * (1 if row.get("direction") == "BULLISH" else -1 if row.get("direction") == "BEARISH" else 0)

                # Deduce regime
                diff_pct = self.diff_oi_pct[inst]
                if diff_pct >= self.config.oi_bullish_threshold:
                    self.oi_regime[inst] = "BULLISH"
                elif diff_pct <= self.config.oi_bearish_threshold:
                    self.oi_regime[inst] = "BEARISH"
                else:
                    self.oi_regime[inst] = "CHOP"

    async def handle_vix(self, data: dict):
        # No publisher currently emits VIX_UPDATE (no live India VIX feed
        # is wired up yet). If/when one is, this marks VIX data as real.
        self._vix_data_received = True
        self.current_vix = data.get("current_vix", self.current_vix)
        vix_1h_ago = data.get("vix_1h_ago", self.current_vix)

        if vix_1h_ago > 0:
            self.vix_1h_change_pct = ((self.current_vix - vix_1h_ago) / vix_1h_ago) * 100
        else:
            self.vix_1h_change_pct = 0.0

        if self.vix_1h_change_pct >= self.config.vix_override_threshold:
            self.vix_override = True
        else:
            self.vix_override = False


gap_opening_engine = GapOpeningEngine()
