"""CAS Dislocation Engine.

Tracks the gap between the frozen cash-market spot (continuous trading
ends ~15:15 IST on expiry day) and the still-trading futures/options
market, scores it, and — only if explicitly configured and armed —
executes through the exact same DECISION_CREATED -> RiskEngine ->
ExecutionEngine -> OrderGateway pipeline every other strategy in this
platform uses. Independent detection logic and its own config/arm switch,
not a separate or faster path to a real order: still DRY_RUN by default,
still needs the broker-level LIVE arm, still passes every risk-limit
check (see risk_limits.check_cas_enabled).

Position lifecycle mirrors manual_trading exactly (PENDING -> OPEN ->
CLOSED, driven by subscribing back to RISK_DECISION/EXECUTION_UPDATE, not
assumed from submitting a decision) for the same reason it was built that
way there: a rejected order must never read as an open position.
"""

import asyncio
import logging
import uuid
from collections import deque
from datetime import datetime, time
from typing import Any, Dict, List, Optional

import pytz

from backend.app.core import upstox_auth
from backend.app.core.event_bus import event_bus
from backend.app.market_data.expiry_calendar import expiry_calendar
from backend.app.market_data.futures_instrument import (
    FuturesInstrumentLookupError,
    futures_instrument_cache,
)
from backend.app.market_data.lot_sizes import get_lot_size
from backend.app.market_data.market_quote import MarketQuoteLookupError, fetch_quote
from backend.app.market_data.option_chain_client import (
    OptionChainLookupError,
    fetch_option_chain,
)
from backend.app.market_data.symbols import INDEX_INSTRUMENT_KEYS
from backend.app.strategies.expiry_engine import find_atm_strike
from backend.app.strategies.manual_trading.analysis import extract_leg, resolve_strike_row

from .analysis import (
    classify_signal,
    compute_dislocation_pct,
    compute_future_displacement,
    compute_future_velocity,
    compute_score,
    compute_spread_quality,
    compute_volume_acceleration,
    is_volatility_shock,
    theoretical_price,
    time_to_expiry_years,
)
from .config_state import cas_config_state
from .models import CASPosition, CASReading, FreezeSnapshot

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

TIGHT_POLL_SECONDS = 2       # inside the watch window: fast, tick-level tracking
COARSE_POLL_SECONDS = 60     # outside it: cheap, infrequent time-gate check only

WATCH_WINDOW_START = time(14, 55, 0)   # start polling a little early to warm up
PRE_CAS_START = time(15, 0, 0)
FREEZE_TIME = time(15, 15, 0)
DISLOCATION_END = time(15, 17, 0)      # per spec: dislocation scoring window is tight
WATCH_WINDOW_END = time(15, 20, 0)     # stop new detection, but exit-monitoring keeps running

VELOCITY_WINDOW_SECONDS = 10.0
SHOCK_RATIO = 3.0
MIN_DISLOCATION_PCT = 0.15
CONFIRMED_STATUSES = ("SUBMITTED", "DRY_RUN")


class CASExecutionError(Exception):
    """Raised when a manual execute-current-signal request can't be honoured."""


class CASDislocationEngine:
    def __init__(self):
        self.latest_reading: Optional[CASReading] = None
        self.snapshot: Optional[FreezeSnapshot] = None
        self.positions: Dict[str, CASPosition] = {}
        self._pending_entries: Dict[str, str] = {}
        self._pending_exits: Dict[str, str] = {}
        self._future_history: deque = deque(maxlen=50)
        self._volume_history_pre_cas: deque = deque(maxlen=60)
        self._last_atm_volume: Optional[float] = None
        self._baseline_ce_ask: Optional[float] = None
        self._baseline_pe_ask: Optional[float] = None
        self._latest_row: Optional[Dict[str, Any]] = None
        self.running = False
        self._task = None

    def start(self):
        if self.running:
            return
        self.running = True
        event_bus.subscribe("RISK_DECISION", self._on_risk_decision)
        event_bus.subscribe("EXECUTION_UPDATE", self._on_execution_update)
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("CAS Dislocation Engine started")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("CAS Dislocation Engine stopped")

    # =====================================================================
    # Poll loop
    # =====================================================================

    async def _poll_loop(self):
        while self.running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in CAS Dislocation Engine tick: {exc}")

            now_t = datetime.now(IST).time()
            sleep_for = TIGHT_POLL_SECONDS if WATCH_WINDOW_START <= now_t <= WATCH_WINDOW_END else COARSE_POLL_SECONDS
            await asyncio.sleep(sleep_for)

    async def _tick(self):
        now_ist = datetime.now(IST)
        now_t = now_ist.time()

        # Open-position exit monitoring runs regardless of the detection
        # window — a position can still be open past 15:17.
        await self._check_position_exits(now_ist)

        if not (WATCH_WINDOW_START <= now_t <= WATCH_WINDOW_END):
            await self._publish_inactive(now_ist, "Outside the CAS watch window (14:55-15:20 IST).")
            self.snapshot = None
            self._future_history.clear()
            self._volume_history_pre_cas.clear()
            self._last_atm_volume = None
            return

        config = cas_config_state.get()
        token = upstox_auth.load_token()
        if not token:
            await self._publish_inactive(now_ist, "No saved Upstox token.")
            return

        try:
            is_expiry = await expiry_calendar.is_today_expiry_day(config.underlying, token)
        except Exception as exc:
            await self._publish_inactive(now_ist, f"Expiry check failed: {exc}")
            return
        if not is_expiry:
            await self._publish_inactive(now_ist, f"Not an expiry day for {config.underlying}.")
            return

        try:
            chain = await fetch_option_chain(INDEX_INSTRUMENT_KEYS[config.underlying], token, "current_week")
            future_key = await futures_instrument_cache.get(config.underlying, token)
            future_quote = await fetch_quote(future_key, token)
        except (OptionChainLookupError, FuturesInstrumentLookupError, MarketQuoteLookupError) as exc:
            await self._publish_inactive(now_ist, f"Data fetch failed: {exc}")
            return

        self._future_history.append((now_ist.timestamp(), future_quote.last_price))

        spot = chain[0].get("underlying_spot_price")
        atm_strike = find_atm_strike(chain, spot)
        row = resolve_strike_row(chain, atm_strike)
        ce_leg, pe_leg = extract_leg(row, "CE"), extract_leg(row, "PE")
        ce_md, pe_md = ce_leg["market_data"], pe_leg["market_data"]
        ce_greeks, pe_greeks = ce_leg.get("option_greeks", {}), pe_leg.get("option_greeks", {})
        atm_volume = (ce_md.get("volume") or 0) + (pe_md.get("volume") or 0)

        if now_t < FREEZE_TIME:
            self._track_pre_cas_volume(atm_volume)
            self.latest_reading = CASReading(
                timestamp=now_ist, state="PRE_CAS", atm_strike=atm_strike, future_price=future_quote.last_price,
            )
            await self._publish_reading()
            return

        if now_t > DISLOCATION_END:
            await self._publish_inactive(now_ist, "Dislocation scoring window closed (past 15:17 IST).")
            return

        if self.snapshot is None:
            self._capture_freeze_snapshot(now_ist, spot, atm_strike, future_quote.last_price, ce_greeks, pe_greeks, ce_md, pe_md)
            self._last_atm_volume = atm_volume
            self.latest_reading = CASReading(
                timestamp=now_ist, state="CAS_FREEZE", frozen_spot=spot, atm_strike=atm_strike,
                future_price=future_quote.last_price,
            )
            await self._publish_reading()
            return

        reading = self._score_dislocation(now_ist, row, ce_md, pe_md, ce_greeks, pe_greeks, atm_volume, future_quote.last_price)
        self.latest_reading = reading
        self._latest_row = row
        await self._publish_reading()

        if reading.state == "SIGNAL" and config.enabled and config.auto_execute and not self._has_active_position():
            await self._execute_signal(reading, row, config)

    def _track_pre_cas_volume(self, atm_volume: float) -> None:
        if self._last_atm_volume is not None:
            self._volume_history_pre_cas.append(max(atm_volume - self._last_atm_volume, 0))
        self._last_atm_volume = atm_volume

    def _capture_freeze_snapshot(self, now_ist, spot, atm_strike, future_price, ce_greeks, pe_greeks, ce_md, pe_md) -> None:
        baseline_rate = (
            sum(self._volume_history_pre_cas) / len(self._volume_history_pre_cas)
            if self._volume_history_pre_cas else 0.0
        )
        self.snapshot = FreezeSnapshot(
            frozen_spot=spot, frozen_at=now_ist, atm_strike=atm_strike, future_price_at_freeze=future_price,
            baseline_ce_iv=(ce_greeks.get("iv") or 0.0) / 100.0,
            baseline_pe_iv=(pe_greeks.get("iv") or 0.0) / 100.0,
            baseline_volume_rate=baseline_rate,
        )
        self._baseline_ce_ask = ce_md.get("ask_price")
        self._baseline_pe_ask = pe_md.get("ask_price")
        logger.info(f"CAS freeze snapshot captured: {self.snapshot}")

    def _score_dislocation(self, now_ist, row, ce_md, pe_md, ce_greeks, pe_greeks, atm_volume, future_price) -> CASReading:
        snapshot = self.snapshot
        tau = time_to_expiry_years(row["expiry"], now_ist.replace(tzinfo=None))
        displacement = compute_future_displacement(snapshot.frozen_spot, future_price)
        velocity = compute_future_velocity(list(self._future_history), VELOCITY_WINDOW_SECONDS)

        ce_theo = theoretical_price(future_price, snapshot.atm_strike, tau, snapshot.baseline_ce_iv, "CE")
        pe_theo = theoretical_price(future_price, snapshot.atm_strike, tau, snapshot.baseline_pe_iv, "PE")
        ce_ask, pe_ask = ce_md.get("ask_price"), pe_md.get("ask_price")
        ce_dislocation = compute_dislocation_pct(ce_theo, ce_ask)
        pe_dislocation = compute_dislocation_pct(pe_theo, pe_ask)

        shock = is_volatility_shock(ce_md.get("ltp"), self._baseline_ce_ask, pe_md.get("ltp"), self._baseline_pe_ask, SHOCK_RATIO)

        delta_volume = max(atm_volume - (self._last_atm_volume or atm_volume), 0)
        self._last_atm_volume = atm_volume
        volume_accel = compute_volume_acceleration(delta_volume, snapshot.baseline_volume_rate)

        ce_spread_q = compute_spread_quality(ce_md.get("bid_price"), ce_ask)
        pe_spread_q = compute_spread_quality(pe_md.get("bid_price"), pe_ask)

        score = compute_score(displacement, velocity, ce_dislocation, pe_dislocation, ce_spread_q, pe_spread_q, volume_accel)
        signal = classify_signal(ce_dislocation, pe_dislocation, shock, MIN_DISLOCATION_PCT)
        config = cas_config_state.get()

        if shock:
            state, reason = "VOLATILITY_SHOCK", "CE and PE both surged from baseline together — blocked, not a directional signal."
        elif signal != "NONE" and score >= config.min_score_to_execute:
            state, reason = "SIGNAL", f"{signal} candidate, score {score} >= execute threshold {config.min_score_to_execute}."
        elif signal != "NONE" and score >= config.min_score_to_alert:
            state, reason = "DISLOCATION", f"{signal} candidate, score {score} below execute threshold {config.min_score_to_execute}."
        else:
            state, reason = "DISLOCATION", "Scanning — no qualifying dislocation yet."

        return CASReading(
            timestamp=now_ist, state=state, frozen_spot=snapshot.frozen_spot,
            future_price=future_price, future_displacement=displacement, future_velocity=velocity,
            atm_strike=snapshot.atm_strike,
            ce_bid=ce_md.get("bid_price"), ce_ask=ce_ask, ce_theoretical=ce_theo, ce_dislocation_pct=ce_dislocation,
            pe_bid=pe_md.get("bid_price"), pe_ask=pe_ask, pe_theoretical=pe_theo, pe_dislocation_pct=pe_dislocation,
            iv_shift_ce=(ce_greeks.get("iv") or 0.0) / 100.0 - snapshot.baseline_ce_iv,
            iv_shift_pe=(pe_greeks.get("iv") or 0.0) / 100.0 - snapshot.baseline_pe_iv,
            volume_acceleration=volume_accel, score=score, signal=signal, reason=reason,
        )

    def _has_active_position(self) -> bool:
        return any(p.status in ("PENDING", "OPEN") for p in self.positions.values())

    async def _publish_inactive(self, now_ist, reason: str) -> None:
        self.latest_reading = CASReading(timestamp=now_ist, state="INACTIVE", reason=reason)
        await self._publish_reading()

    # =====================================================================
    # Execution — same safety pipeline as everything else in this platform
    # =====================================================================

    async def execute_current_signal(self) -> CASPosition:
        """Manual trigger for the trader to confirm the currently-displayed
        signal — the [EXECUTE] button. Works regardless of config.auto_execute
        (a manual click IS the trader's consent in the moment); still
        requires config.enabled, still goes through the same risk gate,
        still refuses a second position while one is already active.
        """
        if self.latest_reading is None or self.latest_reading.signal == "NONE":
            raise CASExecutionError("No active signal to execute.")
        if self.latest_reading.state == "VOLATILITY_SHOCK":
            raise CASExecutionError("Blocked: both legs are repricing together (volatility shock).")
        if self._latest_row is None:
            raise CASExecutionError("No current option chain snapshot to execute against.")
        if self._has_active_position():
            raise CASExecutionError("A CAS position is already PENDING or OPEN.")

        config = cas_config_state.get()
        await self._execute_signal(self.latest_reading, self._latest_row, config)
        return self.positions[next(reversed(self.positions))]

    async def _execute_signal(self, reading: CASReading, row: Dict[str, Any], config) -> None:
        option_type = "CE" if reading.signal == "BUY_CE" else "PE"
        leg = extract_leg(row, option_type)
        instrument_token = leg["instrument_key"]
        entry_price = leg["market_data"]["ltp"]
        lot_size = get_lot_size(config.underlying)
        quantity = config.lots * lot_size

        position_id = f"CAS_{uuid.uuid4().hex[:10]}"
        decision_id = f"{position_id}_ENTRY"

        position = CASPosition(
            position_id=position_id, underlying=config.underlying, option_type=option_type,
            strike=row["strike_price"], instrument_token=instrument_token,
            lots=config.lots, quantity=quantity, entry_price=entry_price,
            max_hold_seconds=config.max_hold_seconds, status="PENDING",
            created_at=datetime.now(IST), last_ltp=entry_price,
        )
        self.positions[position_id] = position
        self._pending_entries[decision_id] = position_id

        await event_bus.publish("DECISION_CREATED", {
            "decision_id": decision_id,
            "instrument": f"{config.underlying} {row['strike_price']} {option_type}",
            "instrument_token": instrument_token,
            "action": "TRADE",
            "transaction_type": "BUY",
            "quantity": quantity,
            "order_type": "MARKET",
            "product": "I",
            "price": entry_price,
            "timestamp": datetime.now(),
            "reasoning": f"CAS dislocation signal, score {reading.score}: {reading.reason}",
            "source": "CAS_DISLOCATION",
        })
        await self._publish_positions()

    async def _close_position(self, position: CASPosition, reason: str) -> None:
        decision_id = f"{position.position_id}_EXIT_{uuid.uuid4().hex[:6]}"
        self._pending_exits[decision_id] = position.position_id
        position.exit_reason = reason

        await event_bus.publish("DECISION_CREATED", {
            "decision_id": decision_id,
            "instrument": f"{position.underlying} {position.strike} {position.option_type}",
            "instrument_token": position.instrument_token,
            "action": "TRADE",
            "transaction_type": "SELL",
            "quantity": position.quantity,
            "order_type": "MARKET",
            "product": "I",
            "price": position.last_ltp or position.entry_price,
            "timestamp": datetime.now(),
            "reasoning": f"CAS exit: {reason}",
            "source": "CAS_DISLOCATION",
        })

    async def close_position_manually(self, position_id: str) -> CASPosition:
        """The [ABORT] button: close an active position immediately,
        independent of max_hold_seconds. Goes through the same
        DECISION_CREATED -> risk -> execution pipeline as every other exit —
        a rejected abort leaves the position OPEN, same as any other exit.
        """
        position = self.positions.get(position_id)
        if position is None:
            raise CASExecutionError(f"No position {position_id!r}.")
        if position.status != "OPEN":
            raise CASExecutionError(f"Position {position_id!r} is not OPEN.")
        await self._close_position(position, reason="MANUAL_ABORT")
        return position

    async def _check_position_exits(self, now_ist: datetime) -> None:
        for position in list(self.positions.values()):
            if position.status != "OPEN" or position.opened_at is None:
                continue
            elapsed = (now_ist - position.opened_at).total_seconds()
            if elapsed >= position.max_hold_seconds:
                await self._close_position(position, reason=f"MAX_HOLD_ELAPSED ({position.max_hold_seconds}s)")

    # =====================================================================
    # Confirmation — mirrors manual_trading's PENDING -> OPEN/CLOSED design
    # =====================================================================

    async def _on_risk_decision(self, risk_dec: Dict[str, Any]) -> None:
        if risk_dec.get("approved"):
            return
        decision_id = risk_dec.get("decision_id")
        reason = risk_dec.get("reason", "Rejected by risk engine.")

        if decision_id in self._pending_entries:
            position_id = self._pending_entries.pop(decision_id)
            position = self.positions.get(position_id)
            if position:
                position.status = "CLOSED"
                position.exit_reason = f"ENTRY_REJECTED: {reason}"
                position.closed_at = datetime.now(IST)
            await self._publish_positions()
        elif decision_id in self._pending_exits:
            position_id = self._pending_exits.pop(decision_id)
            position = self.positions.get(position_id)
            if position:
                position.exit_reason = None
            logger.warning(f"CAS position exit rejected by risk: {reason}")
            await self._publish_positions()

    async def _on_execution_update(self, exec_update: Dict[str, Any]) -> None:
        decision_id = exec_update.get("decision_id")
        status = exec_update.get("status")
        confirmed = status in CONFIRMED_STATUSES

        if decision_id in self._pending_entries:
            position_id = self._pending_entries.pop(decision_id)
            position = self.positions.get(position_id)
            if position is None:
                return
            if confirmed:
                position.status = "OPEN"
                position.opened_at = datetime.now(IST)
            else:
                position.status = "CLOSED"
                position.exit_reason = f"ENTRY_{status}"
                position.closed_at = datetime.now(IST)
            await self._publish_positions()

        elif decision_id in self._pending_exits:
            position_id = self._pending_exits.pop(decision_id)
            position = self.positions.get(position_id)
            if position is None:
                return
            if confirmed:
                position.status = "CLOSED"
                position.closed_at = datetime.now(IST)
            else:
                logger.warning(f"CAS position exit failed at execution: {status}")
                position.exit_reason = None
            await self._publish_positions()

    async def _publish_positions(self) -> None:
        await event_bus.publish("cas_dislocation_positions", {
            "positions": [p.model_dump(mode="json") for p in self.positions.values()],
        })

    async def _publish_reading(self) -> None:
        if self.latest_reading:
            await event_bus.publish("cas_dislocation", self.latest_reading.model_dump(mode="json"))


cas_dislocation_engine = CASDislocationEngine()
