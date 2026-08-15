import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from backend.app.core import upstox_auth
from backend.app.core.event_bus import event_bus
from backend.app.market_data.expiry_calendar import ExpiryLookupError, expiry_calendar
from backend.app.market_data.models import Candle, Tick
from backend.app.strategies.trending_oi_price_action.indicators import DailyATR, SuperTrendIndicator

from .analysis import (
    compute_breakout_stop_loss,
    compute_partial_exit_lots,
    compute_tier_prices,
    detect_oi_shift,
    is_structural_break,
    is_weak_bearish_move,
    is_weak_bullish_move,
    parse_hhmm,
    should_skip_late_session_trade,
)
from .models import ExpiryReversalConfig, ExpiryReversalSignal

logger = logging.getLogger(__name__)


class ExpiryReversalEngine:
    """Expiry Day Reversal Setup.

    Watches for a weak, short-covering-driven up-move getting suddenly
    interrupted by a genuine structural OI shift (call writers entering,
    put writers exiting, or the mirror image), enters a 3-tier ladder on
    the confirmed breakout, protects profit with a partial exit + trailing
    stop, and refuses new entries late in an expiry-day session once the
    day's range has already used up most of the average daily range.
    """

    def __init__(self, config: Optional[ExpiryReversalConfig] = None, strategy_id: str = "expiry_reversal"):
        self.strategy_id = strategy_id
        self.config = config or ExpiryReversalConfig()
        self._late_session_start = parse_hhmm(self.config.late_session_start)

        self.running = False
        self._task = None
        self.positions: Dict[str, Dict[str, Any]] = {}

        # Latest futures OI classification per underlying (from the real
        # trending_oi engine's "future_trending_oi" view).
        self.futures_classification: Dict[str, str] = {}

        # Rolling (timestamp, ce_oi, pe_oi) history per underlying, used to
        # detect the 3-minute OI shift without waiting for a slower refresh.
        self._oi_history: Dict[str, deque] = {}

    def start(self):
        if self.running:
            return
        self.running = True
        event_bus.subscribe("trending_oi", self._handle_trending_oi)
        event_bus.subscribe("CANDLE_CLOSED", self._handle_candle_closed)
        event_bus.subscribe("MARKET_TICK", self._handle_market_tick)
        self._task = asyncio.create_task(self._snapshot_loop())
        logger.info("Expiry Reversal Engine started")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("Expiry Reversal Engine stopped")

    async def _snapshot_loop(self):
        """Periodically publishes the tracked instrument's current state so
        the frontend has fresh data to render even when no new signal has
        fired (position status, weak-move flag, etc. all change without
        necessarily producing a discrete action signal).
        """
        while self.running:
            try:
                await self._refresh_expiry_flag()
                for instrument in list(self.positions.keys()) or ["NIFTY FUT"]:
                    snapshot = self.get_state_snapshot(instrument)
                    await event_bus.publish("expiry_reversal_state", {
                        "instrument": instrument,
                        **snapshot,
                    })
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in ExpiryReversalEngine snapshot loop: {exc}")
                await asyncio.sleep(2)

    async def _refresh_expiry_flag(self):
        """Resolve whether today is the current-week expiry for the
        reference symbol via Upstox's real Instrument Search API.
        ExpiryCalendar caches per IST day, so calling this every snapshot
        tick costs nothing beyond the first successful resolution of the
        day. No saved token, or a failed lookup, leaves is_expiry_day at
        its last known value — never guessed.
        """
        token = upstox_auth.load_token()
        if not token:
            return
        try:
            self.config.is_expiry_day = await expiry_calendar.is_today_expiry_day(
                self.config.expiry_reference_symbol, token,
            )
        except ExpiryLookupError as exc:
            logger.warning(f"Expiry lookup failed, keeping last known value: {exc}")

    def _get_state(self, instrument: str) -> Dict[str, Any]:
        if instrument not in self.positions:
            self.positions[instrument] = {
                "position_state": "WAITING",
                "direction": None,
                "lots_held": 0,
                "avg_entry_price": 0.0,
                "current_sl": 0.0,
                "current_day_high": -float("inf"),
                "current_day_low": float("inf"),
                "current_day_str": "",
                "recent_closes": deque(maxlen=self.config.structural_break_min_candles),
                "recent_opens": deque(maxlen=self.config.structural_break_min_candles),
                "supertrend": SuperTrendIndicator(
                    period=self.config.supertrend_period,
                    multiplier=self.config.supertrend_multiplier,
                ),
                "daily_atr": DailyATR(period=14),
                "tier_1_status": "PENDING",
                "tier_2_status": "PENDING",
                "tier_3_status": "PENDING",
                "partial_exit_done": False,
                "breakeven_done": False,
                "weak_move_active": False,
                "skipped_late_session": False,
            }
        return self.positions[instrument]

    # -----------------------------------------------------------------
    # OI ingestion
    # -----------------------------------------------------------------

    async def _handle_trending_oi(self, data: Dict[str, Any]):
        view = data.get("view")
        underlying = data.get("underlying", "NIFTY")

        if view == "future_trending_oi":
            row = data.get("row", {})
            # FutureTrendingOIEngine emits "LONG BUILDUP" / "SHORT COVERING"
            # etc. with spaces; normalize to the underscore form the rest
            # of this strategy (and the codebase's OI-classification
            # convention) uses.
            classification = row.get("classification", "NEUTRAL").replace(" ", "_")
            self.futures_classification[underlying] = classification
            return

        if view != "spot_trending_oi":
            return

        row = data.get("row", {})
        ce_oi = row.get("ceOi")
        pe_oi = row.get("peOi")
        if ce_oi is None or pe_oi is None:
            return

        history = self._oi_history.setdefault(
            underlying, deque(maxlen=self.config.oi_shift_window_minutes * 60 + 5)
        )
        history.append((datetime.now(), ce_oi, pe_oi))

    def _oi_shift_at(self, underlying: str, now: datetime):
        """Compare current CE/PE OI against the reading closest to
        `oi_shift_window_minutes` ago. Returns (bearish_shift, bullish_shift,
        ce_now, pe_now) or None if there isn't enough history yet.
        """
        history = self._oi_history.get(underlying)
        if not history or len(history) < 2:
            return None

        ce_now = history[-1][1]
        pe_now = history[-1][2]

        window = timedelta(minutes=self.config.oi_shift_window_minutes)
        target_time = now - window

        ce_before, pe_before = history[0][1], history[0][2]
        for ts, ce, pe in history:
            if ts <= target_time:
                ce_before, pe_before = ce, pe
            else:
                break

        bearish, bullish = detect_oi_shift(
            ce_now, ce_before, pe_now, pe_before,
            self.config.call_oi_increase_threshold,
            self.config.put_oi_decrease_threshold,
        )
        return bearish, bullish, ce_now, pe_now

    # -----------------------------------------------------------------
    # Candle ingestion — structural break detection, tiered entries
    # -----------------------------------------------------------------

    async def _handle_candle_closed(self, candle: Candle):
        if candle.timeframe == "1d":
            state = self._get_state(candle.instrument)
            state["daily_atr"].add_daily_candle(candle.high, candle.low, candle.close)
            return

        if candle.timeframe != "3m":
            return

        state = self._get_state(candle.instrument)

        day_str = candle.timestamp.strftime("%Y-%m-%d")
        if state["current_day_str"] != day_str:
            state["current_day_str"] = day_str
            state["current_day_high"] = candle.high
            state["current_day_low"] = candle.low
            prior_day_high = state["current_day_high"]
            prior_day_low = state["current_day_low"]
        else:
            # Snapshot the established range BEFORE folding in this candle:
            # "breaking the day's low" must be checked against the low
            # established by *prior* candles, not a low that already
            # includes the breakout candle itself (which would make a
            # break impossible to ever register).
            prior_day_high = state["current_day_high"]
            prior_day_low = state["current_day_low"]
            state["current_day_high"] = max(state["current_day_high"], candle.high)
            state["current_day_low"] = min(state["current_day_low"], candle.low)

        state["supertrend"].add_candle(candle.high, candle.low, candle.close)
        state["recent_closes"].append(candle.close)
        state["recent_opens"].append(candle.open)

        underlying = candle.instrument.split(" ")[0]
        futures_classification = self.futures_classification.get(underlying, "NEUTRAL")

        daily_atr_val = (
            state["daily_atr"].atr_values[-1] if state["daily_atr"].atr_values else 0.0
        )
        candle_body = candle.close - candle.open

        weak_up = is_weak_bullish_move(
            futures_classification, candle_body, daily_atr_val,
            self.config.weak_candle_body_atr_ratio,
        )
        weak_down = is_weak_bearish_move(
            futures_classification, candle_body, daily_atr_val,
            self.config.weak_candle_body_atr_ratio,
        )
        state["weak_move_active"] = weak_up or weak_down

        if state["position_state"] in ("PARTIAL_EXIT", "TRAILING"):
            await self._trail_stop(candle, state)

        if state["position_state"] != "WAITING":
            return

        oi_result = self._oi_shift_at(underlying, candle.timestamp)
        if oi_result is None:
            return
        bearish_shift, bullish_shift, ce_now, pe_now = oi_result

        broke_low = is_structural_break(
            list(state["recent_closes"]), list(state["recent_opens"]),
            prior_day_low, prior_day_high,
            "BEARISH", self.config.structural_break_min_candles,
        )
        broke_high = is_structural_break(
            list(state["recent_closes"]), list(state["recent_opens"]),
            prior_day_low, prior_day_high,
            "BULLISH", self.config.structural_break_min_candles,
        )

        direction = None
        if bearish_shift and broke_low:
            direction = "BEARISH"
        elif bullish_shift and broke_high:
            direction = "BULLISH"

        if direction is None:
            return

        # E. Time & distance filter: even with a confirmed shift, skip a
        # new entry late in an expiry-day session once the range is
        # exhausted.
        intraday_range = state["current_day_high"] - state["current_day_low"]
        skip, reason = should_skip_late_session_trade(
            self.config.is_expiry_day,
            candle.timestamp.time(),
            self._late_session_start,
            intraday_range,
            daily_atr_val,
            self.config.atr_exhaustion_ratio,
        )
        if skip:
            state["skipped_late_session"] = True
            await self._emit_signal(
                candle.instrument, "SKIP_LATE_SESSION", direction, 0, None, reason,
            )
            return

        await self._enter_tier_1(candle, state, direction)

    async def _enter_tier_1(self, candle: Candle, state: Dict[str, Any], direction: str):
        stop_loss = compute_breakout_stop_loss(
            candle.high, candle.low, direction, self.config.stop_loss_buffer_points,
        )
        tier_1_price, tier_2_price, tier_3_price = compute_tier_prices(
            candle.close, direction,
            self.config.tier_2_offset_points, self.config.tier_3_offset_points,
        )

        state["position_state"] = "TIER_1_ENTERED"
        state["direction"] = direction
        state["lots_held"] = self.config.tier_1_lots
        state["avg_entry_price"] = tier_1_price
        state["current_sl"] = stop_loss
        state["tier_1_status"] = "FILLED"
        state["tier_2_status"] = "PENDING"
        state["tier_3_status"] = "PENDING"
        state["_tier_2_price"] = tier_2_price
        state["_tier_3_price"] = tier_3_price

        await self._emit_signal(
            candle.instrument, "ENTER_TIER_1", direction, self.config.tier_1_lots,
            stop_loss, "Structural OI shift confirmed breakout",
        )

    # -----------------------------------------------------------------
    # Tick ingestion — tier fills, profit protection, trailing, exits
    # -----------------------------------------------------------------

    async def _handle_market_tick(self, tick: Tick):
        instrument = tick.instrument
        if instrument not in self.positions:
            return
        state = self.positions[instrument]

        if state["position_state"] == "TIER_1_ENTERED":
            await self._check_ladder_fills(tick, state)
            await self._check_partial_profit(tick, state)

        if state["position_state"] in (
            "TIER_1_ENTERED", "TIER_2_ENTERED", "TIER_3_ENTERED", "PARTIAL_EXIT", "TRAILING",
        ):
            await self._check_stop_loss(tick, state)

    async def _check_ladder_fills(self, tick: Tick, state: Dict[str, Any]):
        direction = state["direction"]
        tier_2_price = state.get("_tier_2_price")
        tier_3_price = state.get("_tier_3_price")

        if state["tier_2_status"] == "PENDING" and tier_2_price is not None:
            reached = (
                tick.price <= tier_2_price if direction == "BEARISH" else tick.price >= tier_2_price
            )
            if reached:
                state["tier_2_status"] = "FILLED"
                state["lots_held"] += self.config.tier_2_lots
                state["position_state"] = "TIER_2_ENTERED"
                await self._emit_signal(
                    tick.instrument, "ENTER_TIER_2", direction, self.config.tier_2_lots,
                    state["current_sl"], "Tier 2 level reached",
                )

        if state["tier_3_status"] == "PENDING" and tier_3_price is not None:
            reached = (
                tick.price <= tier_3_price if direction == "BEARISH" else tick.price >= tier_3_price
            )
            if reached:
                state["tier_3_status"] = "FILLED"
                state["lots_held"] += self.config.tier_3_lots
                state["position_state"] = "TIER_3_ENTERED"
                await self._emit_signal(
                    tick.instrument, "ENTER_TIER_3", direction, self.config.tier_3_lots,
                    state["current_sl"], "Tier 3 level reached",
                )

    async def _check_partial_profit(self, tick: Tick, state: Dict[str, Any]):
        """D. If price moves favorably right after tier 1 fills (before
        waiting for tiers 2/3 to fill), book partial profit immediately
        and move the stop-loss for the remainder to break-even.
        """
        if state["partial_exit_done"]:
            return
        direction = state["direction"]
        entry = state["avg_entry_price"]
        in_profit = (
            tick.price < entry if direction == "BEARISH" else tick.price > entry
        )
        if not in_profit:
            return

        exit_lots = compute_partial_exit_lots(state["lots_held"], self.config.partial_exit_pct)
        state["lots_held"] -= exit_lots
        state["current_sl"] = entry
        state["partial_exit_done"] = True
        state["breakeven_done"] = True
        state["position_state"] = "PARTIAL_EXIT"
        # Any tiers not yet filled are cancelled once we've locked in profit —
        # the setup no longer needs the deeper ladder.
        state["tier_2_status"] = "CANCELLED" if state["tier_2_status"] == "PENDING" else state["tier_2_status"]
        state["tier_3_status"] = "CANCELLED" if state["tier_3_status"] == "PENDING" else state["tier_3_status"]

        await self._emit_signal(
            tick.instrument, "CANCEL_PENDING_TIERS", direction, 0, None,
            "Profit protection: cancelling unfilled tiers",
        )
        await self._emit_signal(
            tick.instrument, "EXIT_PARTIAL", direction, exit_lots, state["current_sl"],
            f"Booked {self.config.partial_exit_pct:.0f}% profit",
        )
        await self._emit_signal(
            tick.instrument, "TRAIL_SL", direction, state["lots_held"], state["current_sl"],
            "Moved SL to break-even",
        )

    async def _check_stop_loss(self, tick: Tick, state: Dict[str, Any]):
        direction = state["direction"]
        hit = (
            tick.price >= state["current_sl"] if direction == "BEARISH" else tick.price <= state["current_sl"]
        )
        if hit:
            state["position_state"] = "EXITED"
            state["lots_held"] = 0
            await self._emit_signal(
                tick.instrument, "EXIT_ALL", direction, 0, state["current_sl"],
                "Stop loss hit",
            )

    async def _trail_stop(self, candle: Candle, state: Dict[str, Any]):
        """D. "Trail the stop-loss candle-by-candle" — moved on each 3m
        close, not on every tick, so a single favorable tick right after
        the break-even move doesn't immediately re-tighten the stop.
        """
        direction = state["direction"]
        state["position_state"] = "TRAILING"
        if direction == "BEARISH":
            new_sl = min(state["current_sl"], candle.high + self.config.stop_loss_buffer_points)
            if new_sl < state["current_sl"]:
                state["current_sl"] = new_sl
                await self._emit_signal(
                    candle.instrument, "TRAIL_SL", direction, state["lots_held"],
                    state["current_sl"], "Trailing stop loss",
                )
        else:
            new_sl = max(state["current_sl"], candle.low - self.config.stop_loss_buffer_points)
            if new_sl > state["current_sl"]:
                state["current_sl"] = new_sl
                await self._emit_signal(
                    candle.instrument, "TRAIL_SL", direction, state["lots_held"],
                    state["current_sl"], "Trailing stop loss",
                )

    async def _emit_signal(
        self, instrument: str, action: str, direction: Optional[str], lots: int,
        stop_loss: Optional[float], reason: str,
    ):
        signal = ExpiryReversalSignal(
            instrument=instrument,
            action=action,
            direction=direction,
            lots=lots,
            stop_loss=stop_loss,
            reason=reason,
            timestamp=datetime.now(),
        )
        await event_bus.publish("expiry_reversal_signal", signal.model_dump(mode="json"))

    # -----------------------------------------------------------------
    # State snapshot for the live-stream/websocket layer
    # -----------------------------------------------------------------

    def get_state_snapshot(self, instrument: str) -> Dict[str, Any]:
        state = self.positions.get(instrument)
        if state is None:
            return {"status": "NO_ACTIVE_INSTRUMENT_STATE"}

        return {
            "position_state": state["position_state"],
            "direction": state["direction"],
            "lots_held": state["lots_held"],
            "avg_entry_price": state["avg_entry_price"],
            "current_sl": state["current_sl"],
            "tier_1_status": state["tier_1_status"],
            "tier_2_status": state["tier_2_status"],
            "tier_3_status": state["tier_3_status"],
            "partial_exit_done": state["partial_exit_done"],
            "breakeven_done": state["breakeven_done"],
            "weak_move_active": state["weak_move_active"],
            "skipped_late_session": state["skipped_late_session"],
        }


expiry_reversal_engine = ExpiryReversalEngine()
