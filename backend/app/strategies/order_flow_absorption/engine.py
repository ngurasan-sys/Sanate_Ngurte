"""OFAOEngine — orchestrates Context -> Location -> Absorption ->
Dominance -> Confirmation -> Option Selection -> TradeIntent, then hands
off to the EXISTING risk/execution pipeline exactly like
cas_dislocation/engine.py does: publish DECISION_CREATED directly
(source="OFAO"), never call the broker, never branch on LIVE/PAPER (spec
§35 — order_gateway.resolve_mode() is the only thing that decides that,
entirely downstream of this file).

Data source honesty (see docs/order_flow_option_strategy_architecture.md
§2/§23): the only tick source feeding footprint_processor today is
mock_feed.py's simulated generator — there is no real Level-2 futures
feed wired into this app yet. This engine does not know or care whether
its ticks are real or simulated (it shouldn't have to — that's exactly
the kind of environment-awareness spec §35 forbids strategy logic from
having). The safety boundary is `OFAOConfig.enabled` (defaults False,
same as every other strategy config in this codebase) plus
order_gateway's own DRY_RUN default — nothing places a real order until
a human deliberately flips both.

Scope note on position management: TARGET_1 is reached and logged (state
machine + dashboard visibility) but does not trigger a partial-exit
order — the position is fully closed at the final target, the stop, or a
thesis-invalidation exit. Partial profit booking at TARGET_1 is left for
a follow-up pass; flagged here rather than silently simplified.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from backend.app.core import upstox_auth
from backend.app.core.event_bus import event_bus
from backend.app.market_data.lot_sizes import get_lot_size
from backend.app.market_data.option_chain_client import OptionChainLookupError, fetch_option_chain
from backend.app.market_data.symbols import INDEX_INSTRUMENT_KEYS
from backend.app.order_flow.footprint_candle import FootprintCandle
from backend.app.order_flow.footprint_processor import footprint_processor

from .absorption import AbsorptionResult, detect_buyer_absorption, detect_seller_absorption
from .config import OFAOConfig, validate_config
from .dominance import DominanceResult, evaluate_bearish_dominance, evaluate_bullish_dominance
from .fibonacci import compute_retracement_levels
from .location import LocationResult, evaluate_location
from .market_structure import StructureBar, StructureBias, SwingType, classify_structure, find_swing_points, resample_bars
from .models import SetupContext, SetupDirection, SetupState, TERMINAL_STATES, TradeIntent
from .option_selection import extract_candidates_from_chain, select_best_option
from .risk_reward import compute_risk_reward_plan, compute_stop
from .state_machine import InvalidTransitionError, OFAOStateMachine
from .volume_profile import VolumeProfile, compute_volume_profile
from .vwap import compute_session_vwap

logger = logging.getLogger(__name__)

INSTRUMENT_KEY_TO_UNDERLYING = {"NIFTY FUT": "NIFTY", "SENSEX FUT": "SENSEX", "BANKNIFTY FUT": "BANKNIFTY"}

# order_gateway's DRY_RUN mode never reaches a broker, so it can never
# produce a real "SUBMITTED" — but it's still a *confirmed* outcome for
# state-progression purposes (the whole point of DRY_RUN is that the
# strategy pipeline behaves identically whether or not a human has armed
# LIVE). Mirrors cas_dislocation/engine.py's CONFIRMED_STATUSES exactly,
# so OFAO setups don't get stuck in ORDER_SUBMITTED forever whenever the
# codebase is (as it is by default) not armed for LIVE.
OFAO_CONFIRMED_STATUSES = ("SUBMITTED", "DRY_RUN")


class OFAOEngine:
    def __init__(self, config: Optional[OFAOConfig] = None):
        self.config = config or OFAOConfig()
        self.state_machine = OFAOStateMachine()
        self.running = False
        # The state machine's SetupContext stays lightweight/serializable
        # (frontend + persistence read it); the actual FootprintCandle
        # objects an in-flight setup needs for dominance/microstructure
        # checks are kept here instead, off to the side.
        self._absorption_candles: Dict[str, List[FootprintCandle]] = {}
        self._latest_snapshot: Dict[str, dict] = {}
        # decision_id -> instrument_key for exit orders in flight, so
        # _monitor_position never fires a second SELL for the same
        # position while the first is still awaiting execution
        # confirmation (mirrors cas_dislocation's _pending_exits).
        self._pending_exits: Dict[str, str] = {}

    def start(self):
        if self.running:
            return
        self.running = True
        event_bus.subscribe("footprint_candles", self._on_footprint_update)
        event_bus.subscribe("EXECUTION_UPDATE", self._on_execution_update)
        logger.info("OFAOEngine started (enabled=%s)", self.config.enabled)

    def stop(self):
        self.running = False
        logger.info("OFAOEngine stopped")

    def configure(self, config: OFAOConfig) -> OFAOConfig:
        validate_config(config)
        # Reconfiguring always disarms — a config change must never
        # silently keep a different, stale setup armed under parameters
        # nobody confirmed (same rule as CASConfigState/AlgoConfigState).
        self.config = config.model_copy(update={"enabled": False, "updated_at": datetime.now(timezone.utc)})
        return self.config

    def enable(self) -> OFAOConfig:
        self.config.enabled = True
        return self.config

    def disable(self) -> OFAOConfig:
        self.config.enabled = False
        return self.config

    def get_snapshot(self, instrument_key: str) -> Optional[dict]:
        return self._latest_snapshot.get(instrument_key)

    def get_open_position_blocker(self) -> Optional[str]:
        active = [
            instrument for instrument, ctx in self.state_machine._contexts.items()
            if ctx.state != SetupState.NO_SETUP and ctx.state not in TERMINAL_STATES
        ]
        if not active:
            return None
        return f"{len(active)} active setup(s): {', '.join(active)}."

    # -----------------------------------------------------------------
    # Event bus wiring
    # -----------------------------------------------------------------

    async def _on_footprint_update(self, payload: dict) -> None:
        instrument_key = payload.get("instrument_key")
        underlying = INSTRUMENT_KEY_TO_UNDERLYING.get(instrument_key)
        if underlying is None or underlying not in self.config.underlyings:
            return
        try:
            await self.evaluate(instrument_key, underlying)
        except Exception:
            logger.exception("Error evaluating OFAO cycle for %s", instrument_key)

    async def _on_execution_update(self, update: dict) -> None:
        decision_id = update.get("decision_id") or ""

        # Exit orders are tracked by decision_id, not by setup_id parsing
        # (their decision_id carries an "_EXIT_<suffix>" tail) — check
        # this first so an exit update never falls through to the entry
        # matching below.
        if decision_id in self._pending_exits:
            instrument_key = self._pending_exits.pop(decision_id)
            await self._handle_exit_update(instrument_key, update)
            return

        if not decision_id.startswith("OFAO_"):
            return
        setup_id = decision_id[len("OFAO_"):]
        for instrument_key in list(self.state_machine._contexts.keys()):
            ctx = self.state_machine.get(instrument_key)
            if ctx.setup_id == setup_id and ctx.state == SetupState.ORDER_SUBMITTED:
                await self._handle_execution_update(instrument_key, update)
                return

    async def _handle_execution_update(self, instrument_key: str, update: dict) -> None:
        status = update.get("status")
        if status in OFAO_CONFIRMED_STATUSES:
            self.state_machine.transition(instrument_key, SetupState.ORDER_FILLED)
            self.state_machine.transition(instrument_key, SetupState.POSITION_ACTIVE)
        elif status in ("REJECTED", "ERROR"):
            self.state_machine.transition(instrument_key, SetupState.CANCELLED)
            self.state_machine.reset(instrument_key, reason=f"Execution {status}: {update.get('detail')}")
            self._absorption_candles.pop(instrument_key, None)

    async def _handle_exit_update(self, instrument_key: str, update: dict) -> None:
        status = update.get("status")
        ctx = self.state_machine.get(instrument_key)
        if status in OFAO_CONFIRMED_STATUSES:
            if ctx.state in (SetupState.POSITION_ACTIVE, SetupState.TARGET_1, SetupState.TARGET_2):
                self.state_machine.transition(instrument_key, SetupState.EXITED)
            self.state_machine.reset(instrument_key, reason="Position closed.")
            self._absorption_candles.pop(instrument_key, None)
        else:
            logger.warning("%s: exit order failed at execution (%s) — position remains open, will retry.", instrument_key, status)

    # -----------------------------------------------------------------
    # Core evaluation cycle — one per footprint update per instrument
    # -----------------------------------------------------------------

    async def evaluate(self, instrument_key: str, underlying: str) -> None:
        if not self.config.enabled:
            return

        now = datetime.now(timezone.utc)
        candles = self._get_candles(instrument_key)
        if not candles:
            return  # no data yet — never evaluate against nothing

        if self.state_machine.has_active_setup(instrument_key):
            await self._advance_setup(instrument_key, underlying, candles, now)
        else:
            self._scan_for_new_setup(instrument_key, underlying, candles, now)

        await self._update_snapshot(instrument_key, underlying, candles, now)

    def _get_candles(self, instrument_key: str) -> List[FootprintCandle]:
        history = footprint_processor.aggregator.get_history(instrument_key, self.config.footprint_timeframe)
        current = footprint_processor.aggregator.get_current(instrument_key, self.config.footprint_timeframe)
        return list(history) + ([current] if current else [])

    def _get_structure_bars(self, instrument_key: str) -> List[StructureBar]:
        history = footprint_processor.aggregator.get_history(instrument_key, self.config.structure_base_timeframe)
        return [StructureBar(high=c.high, low=c.low, close=c.close) for c in history]

    def _is_within_entry_window(self, now: datetime) -> bool:
        now_t = now.time()
        start = datetime.strptime(self.config.entry_start_time, "%H:%M").time()
        cutoff = datetime.strptime(self.config.entry_cutoff_time, "%H:%M").time()
        return start <= now_t < cutoff

    def _compute_context(self, instrument_key: str) -> StructureBias:
        bars = self._get_structure_bars(instrument_key)
        if not bars:
            return StructureBias.UNKNOWN
        bars_1h = resample_bars(bars, self.config.structure_1h_bars)
        bars_4h = resample_bars(bars, self.config.structure_4h_bars)
        bias_1h = classify_structure(bars_1h)
        bias_4h = classify_structure(bars_4h)
        if bias_1h == StructureBias.UNKNOWN or bias_4h == StructureBias.UNKNOWN:
            return StructureBias.UNKNOWN
        if bias_1h == StructureBias.BULLISH and bias_4h == StructureBias.BULLISH:
            return StructureBias.BULLISH
        if bias_1h == StructureBias.BEARISH and bias_4h == StructureBias.BEARISH:
            return StructureBias.BEARISH
        return StructureBias.BALANCED

    def _compute_location(self, instrument_key: str, candles: List[FootprintCandle], price: float):
        profile = compute_volume_profile(candles, self.config.value_area_pct)
        bars = self._get_structure_bars(instrument_key)
        swings = find_swing_points(bars) if bars else []
        swing_highs = [s.price for s in swings if s.type == SwingType.HIGH]
        swing_lows = [s.price for s in swings if s.type == SwingType.LOW]
        swing_high = swing_highs[-1] if swing_highs else None
        swing_low = swing_lows[-1] if swing_lows else None

        fib_discount = fib_premium = None
        if swing_high is not None and swing_low is not None and swing_high > swing_low:
            fib_discount = compute_retracement_levels(swing_high, swing_low, "DISCOUNT")
            fib_premium = compute_retracement_levels(swing_high, swing_low, "PREMIUM")

        vwap = compute_session_vwap(candles)

        # previous_day_high/low and a prior session's volume profile are
        # honestly unavailable today — no persisted cross-session
        # footprint history exists (architecture doc §24). Never guessed.
        location = evaluate_location(
            price=price, current_profile=profile, previous_profile=None,
            previous_day_high=None, previous_day_low=None,
            swing_high=swing_high, swing_low=swing_low,
            fib_discount=fib_discount, fib_premium=fib_premium, vwap=vwap,
            proximity_pct=self.config.location_proximity_pct,
        )
        return location, profile, swing_high, swing_low

    def _scan_for_new_setup(self, instrument_key: str, underlying: str, candles: List[FootprintCandle], now: datetime) -> None:
        price = candles[-1].close
        context = self._compute_context(instrument_key)

        if context == StructureBias.UNKNOWN:
            logger.debug("%s: NO TRADE — higher timeframe context UNKNOWN.", instrument_key)
            return

        if not self._is_within_entry_window(now):
            logger.debug("%s: NO TRADE — outside entry window.", instrument_key)
            return

        location, profile, swing_high, swing_low = self._compute_location(instrument_key, candles, price)

        if context == StructureBias.BULLISH and location.is_bullish_location:
            self.state_machine.transition(
                instrument_key, SetupState.LOCATION_REACHED, now=now,
                direction=SetupDirection.BULL, location_price=price,
                location_reason=",".join(location.matched_bullish_factors),
            )
            self._absorption_candles[instrument_key] = []
        elif context == StructureBias.BEARISH and location.is_bearish_location:
            self.state_machine.transition(
                instrument_key, SetupState.LOCATION_REACHED, now=now,
                direction=SetupDirection.BEAR, location_price=price,
                location_reason=",".join(location.matched_bearish_factors),
            )
            self._absorption_candles[instrument_key] = []
        else:
            logger.debug("%s: NO TRADE — no valid location for context %s.", instrument_key, context.value)

    async def _advance_setup(self, instrument_key: str, underlying: str, candles: List[FootprintCandle], now: datetime) -> None:
        ctx = self.state_machine.get(instrument_key)

        if ctx.state == SetupState.LOCATION_REACHED:
            self._evaluate_absorption(instrument_key, ctx, candles, now)
        elif ctx.state == SetupState.ABSORPTION_DETECTED:
            self.state_machine.transition(instrument_key, SetupState.WAITING_FOR_DOMINANCE, now=now)
        elif ctx.state == SetupState.WAITING_FOR_DOMINANCE:
            self._evaluate_dominance(instrument_key, ctx, candles, now)
        elif ctx.state == SetupState.DOMINANCE_CONFIRMED:
            self._build_signal(instrument_key, underlying, ctx, candles, now)
        elif ctx.state == SetupState.SIGNAL_READY:
            await self._execute_signal(instrument_key, underlying, ctx, candles, now)
        # ORDER_SUBMITTED/ORDER_FILLED/POSITION_ACTIVE/TARGET_1/TARGET_2
        # advance from _on_execution_update and _monitor_position, not here.
        if ctx.state == SetupState.POSITION_ACTIVE or ctx.state == SetupState.TARGET_1:
            await self._monitor_position(instrument_key, ctx, candles, now)

    def _window_candles(self, candles: List[FootprintCandle], n: int) -> List[FootprintCandle]:
        return candles[-n:] if len(candles) >= n else candles

    def _evaluate_absorption(self, instrument_key: str, ctx: SetupContext, candles: List[FootprintCandle], now: datetime) -> None:
        window = self._window_candles(candles, self.config.absorption_window_candles)
        deltas = [c.delta for c in candles[:-len(window)]] if len(candles) > len(window) else []
        volumes = [c.buy_volume + c.sell_volume for c in candles[:-len(window)]] if len(candles) > len(window) else []

        if ctx.direction == SetupDirection.BULL:
            result = detect_seller_absorption(
                window, ctx.location_price, min_candles=self.config.min_absorption_candles,
                location_tolerance_pct=self.config.absorption_location_tolerance_pct,
                max_break_pct=self.config.absorption_max_break_pct,
                delta_history=deltas or None, volume_history=volumes or None,
            )
        else:
            result = detect_buyer_absorption(
                window, ctx.location_price, min_candles=self.config.min_absorption_candles,
                location_tolerance_pct=self.config.absorption_location_tolerance_pct,
                max_break_pct=self.config.absorption_max_break_pct,
                delta_history=deltas or None, volume_history=volumes or None,
            )

        if result.detected and result.strength >= self.config.absorption_strength_threshold:
            self.state_machine.transition(
                instrument_key, SetupState.ABSORPTION_DETECTED, now=now,
                absorption_strength=result.strength, invalidation_price=result.defended_price,
            )
            self._absorption_candles[instrument_key] = list(window)
        elif result.detected:
            logger.debug(
                "%s: absorption pattern present but strength %.1f below threshold %.1f.",
                instrument_key, result.strength, self.config.absorption_strength_threshold,
            )

    def _evaluate_dominance(self, instrument_key: str, ctx: SetupContext, candles: List[FootprintCandle], now: datetime) -> None:
        absorption_window = self._absorption_candles.get(instrument_key, [])
        if not absorption_window:
            return
        last_absorption_time = absorption_window[-1].open_time
        confirmation = [c for c in candles if c.open_time > last_absorption_time]
        confirmation = self._window_candles(confirmation, self.config.dominance_window_candles)
        if not confirmation:
            return

        if ctx.direction == SetupDirection.BULL:
            result = evaluate_bullish_dominance(absorption_window, confirmation, self.config.imbalance_ratio_pct)
        else:
            result = evaluate_bearish_dominance(absorption_window, confirmation, self.config.imbalance_ratio_pct)

        if result.confirmed:
            self.state_machine.transition(instrument_key, SetupState.DOMINANCE_CONFIRMED, now=now)
        elif len(confirmation) >= self.config.dominance_window_candles and not result.opposing_aggression:
            # Watched long enough with no opposing aggression at all —
            # the thesis isn't developing; give up rather than wait forever.
            self.state_machine.transition(instrument_key, SetupState.INVALIDATED, now=now)
            self._absorption_candles.pop(instrument_key, None)

    def _build_signal(self, instrument_key: str, underlying: str, ctx: SetupContext, candles: List[FootprintCandle], now: datetime) -> None:
        entry = candles[-1].close
        direction = "BULL" if ctx.direction == SetupDirection.BULL else "BEAR"
        stop = compute_stop(ctx.invalidation_price, direction, self.config.stop_buffer_pct)

        try:
            plan = compute_risk_reward_plan(entry, stop, direction, self.config.target_r_multiple)
        except ValueError as exc:
            logger.info("%s: NO TRADE — %s", instrument_key, exc)
            self.state_machine.transition(instrument_key, SetupState.INVALIDATED, now=now)
            self._absorption_candles.pop(instrument_key, None)
            return

        if plan.risk_reward < self.config.risk_reward_min:
            logger.info(
                "%s: NO TRADE — R:R %.2f below minimum %.2f.",
                instrument_key, plan.risk_reward, self.config.risk_reward_min,
            )
            self.state_machine.transition(instrument_key, SetupState.INVALIDATED, now=now)
            self._absorption_candles.pop(instrument_key, None)
            return

        option_type = "CE" if ctx.direction == SetupDirection.BULL else "PE"
        atm_strike = round(entry / self.config.strike_step) * self.config.strike_step

        trade_intent = TradeIntent(
            setup_id=ctx.setup_id, timestamp=now, underlying=underlying, direction="BUY",
            option_type=option_type, strike=atm_strike, expiry="UNRESOLVED", quantity=0,
            underlying_trigger=entry, underlying_stop=stop, underlying_target=plan.target,
            risk_reward=plan.risk_reward, score=11, confidence="A+" if ctx.absorption_strength >= 85 else "A",
            reason=(
                f"{'Seller' if ctx.direction == SetupDirection.BULL else 'Buyer'} absorption "
                f"(strength {ctx.absorption_strength:.0f}) + dominance shift + microstructure break."
            ),
            location=ctx.location_reason or "", absorption_strength=ctx.absorption_strength,
            imbalance_ratio_pct=self.config.imbalance_ratio_pct,
        )
        self.state_machine.transition(instrument_key, SetupState.SIGNAL_READY, now=now, trade_intent=trade_intent)

    async def _execute_signal(self, instrument_key: str, underlying: str, ctx: SetupContext, candles: List[FootprintCandle], now: datetime) -> None:
        if self.state_machine.is_signal_stale(instrument_key, self.config.signal_timeout_seconds, now):
            logger.info("%s: signal %s expired without execution — cancelling.", instrument_key, ctx.setup_id)
            self.state_machine.transition(instrument_key, SetupState.CANCELLED, now=now)
            self.state_machine.reset(instrument_key, reason="Signal timed out.", now=now)
            self._absorption_candles.pop(instrument_key, None)
            return

        current_price = candles[-1].close
        drift_pct = abs(current_price - ctx.trade_intent.underlying_trigger) / abs(ctx.trade_intent.underlying_trigger)
        if drift_pct > self.config.max_underlying_drift_pct:
            logger.info("%s: underlying drifted %.4f%% from trigger — signal expired.", instrument_key, drift_pct * 100)
            self.state_machine.transition(instrument_key, SetupState.CANCELLED, now=now)
            self.state_machine.reset(instrument_key, reason="Underlying drifted from trigger.", now=now)
            self._absorption_candles.pop(instrument_key, None)
            return

        await self._resolve_and_submit(instrument_key, underlying, ctx, now)

    async def _resolve_and_submit(self, instrument_key: str, underlying: str, ctx: SetupContext, now: datetime) -> None:
        """Spec §22's 15-point final safety check, condensed to what's
        actually checkable in this codebase today — every check that
        fails returns ORDER_BLOCKED with a reason instead of submitting.
        """
        intent = ctx.trade_intent
        if intent is None:
            return

        token = upstox_auth.load_token()
        if not token:
            self._block_order(instrument_key, ctx, "No Upstox token — cannot resolve option chain.", now)
            return

        index_key = INDEX_INSTRUMENT_KEYS.get(underlying)
        if index_key is None:
            self._block_order(instrument_key, ctx, f"No index instrument key configured for {underlying}.", now)
            return

        try:
            chain = await fetch_option_chain(index_key, token, "current_week")
        except OptionChainLookupError as exc:
            self._block_order(instrument_key, ctx, f"Option chain fetch failed: {exc}", now)
            return

        candidates = extract_candidates_from_chain(chain, underlying, expiry="current_week", quote_fetched_at=now, now=now)
        best = select_best_option(
            candidates, intent.option_type, intent.strike, self.config.strike_step,
            self.config.max_spread_pct, self.config.min_oi, 0, self.config.max_quote_age_seconds,
        )
        if best is None:
            self._block_order(instrument_key, ctx, "No liquid ATM/ITM contract found.", now)
            return

        quantity = self.config.lots * get_lot_size(underlying)

        # The signal was built before the option chain was resolved, so
        # TradeIntent.quantity was a placeholder (0) and it never carried
        # the actual tradable contract's instrument_token. Fill both in
        # now so _close_position has what it needs to send a real SELL
        # for exactly this contract/quantity later — never guessed or
        # re-derived from the (possibly stale) chain at exit time.
        resolved_intent = intent.model_copy(update={
            "quantity": quantity,
            "option_instrument_token": best.instrument_key,
        })

        decision_id = f"OFAO_{ctx.setup_id}"
        await event_bus.publish("DECISION_CREATED", {
            "decision_id": decision_id,
            "instrument": f"{underlying} {best.strike} {best.option_type}",
            "instrument_token": best.instrument_key,
            "action": "TRADE",
            "transaction_type": "BUY",
            "quantity": quantity,
            "order_type": "MARKET",
            "product": "I",
            "price": best.ask or best.last_price or 0.0,
            "timestamp": now,
            "reasoning": intent.reason,
            "source": "OFAO",
        })
        self.state_machine.transition(instrument_key, SetupState.ORDER_SUBMITTED, now=now, trade_intent=resolved_intent)

    def _block_order(self, instrument_key: str, ctx: SetupContext, reason: str, now: datetime) -> None:
        logger.warning("%s: ORDER_BLOCKED (setup_id=%s): %s", instrument_key, ctx.setup_id, reason)
        self.state_machine.transition(instrument_key, SetupState.CANCELLED, now=now)
        self.state_machine.reset(instrument_key, reason=reason, now=now)
        self._absorption_candles.pop(instrument_key, None)

    async def _monitor_position(self, instrument_key: str, ctx: SetupContext, candles: List[FootprintCandle], now: datetime) -> None:
        if ctx.trade_intent is None:
            return
        # An exit for this instrument is already awaiting execution
        # confirmation — never fire a second SELL for the same position
        # just because the price is still past stop/target on the next
        # evaluate() cycle.
        if instrument_key in self._pending_exits.values():
            return

        price = candles[-1].close
        is_bull = ctx.direction == SetupDirection.BULL
        intent = ctx.trade_intent

        stop_hit = price <= intent.underlying_stop if is_bull else price >= intent.underlying_stop
        target_hit = price >= intent.underlying_target if is_bull else price <= intent.underlying_target

        if stop_hit:
            await self._close_position(instrument_key, ctx, price, "Stop hit.", now)
            return

        if target_hit:
            if ctx.state == SetupState.POSITION_ACTIVE:
                self.state_machine.transition(instrument_key, SetupState.TARGET_1, now=now)
            else:
                await self._close_position(instrument_key, ctx, price, "Target hit.", now)

    async def _close_position(self, instrument_key: str, ctx: SetupContext, last_price: float, reason: str, now: datetime) -> None:
        """Publish the SELL that actually closes an open OFAO position
        through the existing execution pipeline — mirrors
        cas_dislocation/engine.py's _close_position(). The state machine
        only reaches EXITED/reset once _handle_exit_update confirms the
        order, not the instant stop/target is observed; that's what
        _pending_exits guards against being fired twice for.
        """
        intent = ctx.trade_intent
        if intent is None or intent.option_instrument_token is None:
            logger.warning("%s: cannot close position — no resolved option contract on trade_intent.", instrument_key)
            return

        decision_id = f"OFAO_{ctx.setup_id}_EXIT_{uuid.uuid4().hex[:6]}"
        self._pending_exits[decision_id] = instrument_key

        await event_bus.publish("DECISION_CREATED", {
            "decision_id": decision_id,
            "instrument": f"{intent.underlying} {intent.strike} {intent.option_type}",
            "instrument_token": intent.option_instrument_token,
            "action": "TRADE",
            "transaction_type": "SELL",
            "quantity": intent.quantity,
            "order_type": "MARKET",
            "product": "I",
            "price": last_price,
            "timestamp": now,
            "reasoning": f"OFAO exit: {reason}",
            "source": "OFAO",
        })

    # -----------------------------------------------------------------
    # Dashboard snapshot
    # -----------------------------------------------------------------

    async def _update_snapshot(self, instrument_key: str, underlying: str, candles: List[FootprintCandle], now: datetime) -> None:
        ctx = self.state_machine.get(instrument_key)
        previous = self._latest_snapshot.get(instrument_key)
        state_changed = previous is None or previous.get("state") != ctx.state.value

        snapshot = {
            "instrument_key": instrument_key,
            "underlying": underlying,
            "timestamp": now.isoformat(),
            "state": ctx.state.value,
            "setup_id": ctx.setup_id,
            "direction": ctx.direction.value if ctx.direction else None,
            "location_price": ctx.location_price,
            "location_reason": ctx.location_reason,
            "absorption_strength": ctx.absorption_strength,
            "invalidation_price": ctx.invalidation_price,
            "trade_intent": ctx.trade_intent.model_dump(mode="json") if ctx.trade_intent else None,
            "last_price": candles[-1].close if candles else None,
        }
        self._latest_snapshot[instrument_key] = snapshot

        # Broadcast every cycle (the websocket/dashboard wants a live feed,
        # not just transitions) but only persist a row on an actual state
        # change — every 500ms would flood the DB for no benefit (spec
        # §39's own "log state transitions, not every unchanged state").
        await event_bus.publish("ofao_state", snapshot)
        if state_changed:
            await event_bus.publish("persist_ofao_setup", snapshot)
            logger.info("%s %s -> %s (setup_id=%s)", instrument_key, previous.get("state") if previous else "-", ctx.state.value, ctx.setup_id)


ofao_engine = OFAOEngine()
