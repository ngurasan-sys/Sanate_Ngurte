"""Manual order placement, pyramiding, and SL/target auto-exit.

Every order this engine places — the initial entry, a pyramid add, or an
SL/target-triggered exit — goes through the exact same DECISION_CREATED ->
RiskEngine -> ExecutionEngine -> OrderGateway pipeline the automated
strategies use. There is no separate/faster path to the broker here: a
manual order still defaults to DRY_RUN, still needs both the
EXECUTION_MODE=LIVE env var and the runtime arm switch to actually
reach a broker, and still passes through every real risk-limit check
(quantity cap, max open positions, daily loss, daily order count, market
hours, kill switch). "Manual" describes who chose the trade, not a
different safety model.

Position state is never assumed from submitting a DECISION_CREATED event —
it's driven by subscribing back to RISK_DECISION and EXECUTION_UPDATE, the
same way RiskEngine/ExecutionEngine react to their own inputs. A position
starts PENDING and only becomes OPEN once risk approves AND execution
confirms (SUBMITTED or DRY_RUN); a risk rejection or a broker-side
REJECTED/ERROR takes it straight to CLOSED with the real reason. This
matters concretely: without it, a risk-rejected order (e.g. placed outside
market hours) would sit in the UI as an "OPEN" position that was never
actually accepted anywhere — confirmed live against this exact engine
before this fix existed.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.core import upstox_auth
from backend.app.core.event_bus import event_bus
from backend.app.market_data.lot_sizes import LOT_SIZES, get_lot_size
from backend.app.market_data.option_chain_client import (
    OptionChainLookupError,
    fetch_option_chain,
)
from backend.app.market_data.symbols import INDEX_INSTRUMENT_KEYS
from backend.app.strategies.expiry_engine import find_atm_strike

from .analysis import compute_weighted_entry_price, extract_leg, resolve_strike_row, should_exit
from .models import ManualOrderRequest, ManualPosition

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5
CONFIRMED_STATUSES = ("SUBMITTED", "DRY_RUN")


class ManualTradingError(Exception):
    """Raised when a manual order/pyramid/close request can't be honoured —
    unknown underlying, no token, chain lookup failure, unknown position,
    or a nonsensical SL/target."""


class ManualTradingEngine:
    def __init__(self):
        self.positions: Dict[str, ManualPosition] = {}
        # decision_id -> correlation data, so RISK_DECISION/EXECUTION_UPDATE
        # (which only carry decision_id) can be routed back to the right
        # position and the right kind of pending action.
        self._pending_entries: Dict[str, str] = {}            # decision_id -> position_id
        self._pending_pyramids: Dict[str, Dict[str, Any]] = {}  # decision_id -> {position_id, add_qty, add_price, add_lots}
        self._pending_exits: Dict[str, str] = {}               # decision_id -> position_id
        self.running = False
        self._task = None

    def start(self):
        if self.running:
            return
        self.running = True
        event_bus.subscribe("RISK_DECISION", self._on_risk_decision)
        event_bus.subscribe("EXECUTION_UPDATE", self._on_execution_update)
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Manual Trading Engine started (SL/target monitor)")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("Manual Trading Engine stopped")

    def _require_lot_size(self, underlying: str) -> int:
        try:
            return get_lot_size(underlying)
        except KeyError:
            raise ManualTradingError(
                f"No known lot size for underlying {underlying!r}. Supported: "
                f"{sorted(LOT_SIZES.keys())}."
            )

    async def _require_token(self) -> str:
        token = upstox_auth.load_token()
        if not token:
            raise ManualTradingError(
                "No saved Upstox token — log in via /api/v1/broker/upstox/login."
            )
        return token

    async def _fetch_chain(self, underlying: str, expiry_date: str, token: str) -> List[Dict[str, Any]]:
        if underlying not in INDEX_INSTRUMENT_KEYS:
            raise ManualTradingError(
                f"Unsupported underlying {underlying!r}. Supported: "
                f"{sorted(INDEX_INSTRUMENT_KEYS.keys())}."
            )
        instrument_key = INDEX_INSTRUMENT_KEYS[underlying]
        try:
            return await fetch_option_chain(instrument_key, token, expiry_date)
        except OptionChainLookupError as exc:
            # "current_week" legitimately returns zero rows for some
            # underlyings/times (verified against the live API — same
            # quirk option_analytics/engine.py already works around), so
            # fall back to the next real expiry rather than surfacing that
            # as a hard failure to a trader trying to place an order.
            if expiry_date == "current_week":
                try:
                    return await fetch_option_chain(instrument_key, token, "next_week")
                except OptionChainLookupError as fallback_exc:
                    raise ManualTradingError(
                        f"Option chain fetch failed for {underlying} (tried current_week "
                        f"and next_week): {fallback_exc}"
                    )
            raise ManualTradingError(f"Option chain fetch failed for {underlying}: {exc}")

    async def place_order(self, request: ManualOrderRequest) -> ManualPosition:
        if request.lots <= 0:
            raise ManualTradingError("lots must be a positive integer.")
        if request.pyramid_lot_size < 0:
            raise ManualTradingError("pyramid_lot_size cannot be negative.")
        if not (request.stop_loss < request.target):
            raise ManualTradingError(
                f"stop_loss ({request.stop_loss}) must be less than target "
                f"({request.target}) for a long premium position."
            )

        lot_size = self._require_lot_size(request.underlying)
        token = await self._require_token()
        chain = await self._fetch_chain(request.underlying, request.expiry_date, token)

        spot = chain[0].get("underlying_spot_price")
        strike = request.strike if request.strike is not None else find_atm_strike(chain, spot)
        row = resolve_strike_row(chain, strike)
        if row is None:
            raise ManualTradingError(f"No strikes available in the {request.underlying} chain.")

        leg = extract_leg(row, request.option_type)
        # instrument_key is a sibling of market_data in the real Upstox
        # response (verified live), not nested inside it — the fixture
        # shape used elsewhere in this repo's tests has this wrong.
        instrument_token = leg["instrument_key"]
        entry_price = leg["market_data"]["ltp"]

        quantity = request.lots * lot_size
        position_id = f"MANUAL_{uuid.uuid4().hex[:10]}"
        decision_id = f"{position_id}_ENTRY"

        position = ManualPosition(
            position_id=position_id,
            underlying=request.underlying,
            option_type=request.option_type,
            strike=row["strike_price"],
            instrument_token=instrument_token,
            expiry_date=request.expiry_date,
            lots=request.lots,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=request.stop_loss,
            target=request.target,
            pyramid_lot_size=request.pyramid_lot_size,
            status="PENDING",
            created_at=datetime.now(),
            last_ltp=entry_price,
        )
        self.positions[position_id] = position
        self._pending_entries[decision_id] = position_id

        await self._submit_decision(
            decision_id=decision_id,
            instrument=f"{request.underlying} {row['strike_price']} {request.option_type}",
            instrument_token=instrument_token,
            quantity=quantity,
            transaction_type="BUY",
            price=entry_price,
        )
        await self._publish_positions()
        return position

    async def add_pyramid(self, position_id: str) -> ManualPosition:
        position = self.positions.get(position_id)
        if position is None:
            raise ManualTradingError(f"No position {position_id!r}.")
        if position.status != "OPEN":
            raise ManualTradingError(f"Position {position_id!r} is not OPEN.")
        if position.pyramid_lot_size <= 0:
            raise ManualTradingError(f"Position {position_id!r} has pyramiding disabled (pyramid_lot_size=0).")

        token = await self._require_token()
        chain = await self._fetch_chain(position.underlying, position.expiry_date, token)
        row = resolve_strike_row(chain, position.strike)
        if row is None:
            raise ManualTradingError(f"Strike {position.strike} no longer in the {position.underlying} chain.")
        leg = extract_leg(row, position.option_type)
        current_price = leg["market_data"]["ltp"]

        lot_size = self._require_lot_size(position.underlying)
        add_qty = position.pyramid_lot_size * lot_size
        decision_id = f"{position_id}_PYRAMID_{uuid.uuid4().hex[:6]}"

        self._pending_pyramids[decision_id] = {
            "position_id": position_id,
            "add_qty": add_qty,
            "add_price": current_price,
            "add_lots": position.pyramid_lot_size,
        }

        await self._submit_decision(
            decision_id=decision_id,
            instrument=f"{position.underlying} {position.strike} {position.option_type}",
            instrument_token=position.instrument_token,
            quantity=add_qty,
            transaction_type="BUY",
            price=current_price,
        )
        # Quantity/entry_price update is deferred to _on_execution_update —
        # a pyramid add that gets rejected must not have already inflated
        # the position's tracked size.
        return position

    async def close_position(self, position_id: str, reason: str = "MANUAL_CLOSE") -> ManualPosition:
        position = self.positions.get(position_id)
        if position is None:
            raise ManualTradingError(f"No position {position_id!r}.")
        if position.status != "OPEN":
            raise ManualTradingError(f"Position {position_id!r} is not OPEN.")

        decision_id = f"{position_id}_EXIT_{uuid.uuid4().hex[:6]}"
        self._pending_exits[decision_id] = position_id
        # Stash the intended reason on the position now (STOP_LOSS_HIT /
        # TARGET_HIT / MANUAL_CLOSE) so _on_execution_update can commit it
        # once the exit is actually confirmed, without threading `reason`
        # through the event payload.
        position.exit_reason = reason

        await self._submit_decision(
            decision_id=decision_id,
            instrument=f"{position.underlying} {position.strike} {position.option_type}",
            instrument_token=position.instrument_token,
            quantity=position.quantity,
            transaction_type="SELL",
            price=position.last_ltp or position.entry_price,
        )
        # Status stays OPEN until execution confirms the exit — see
        # _on_execution_update. A rejected exit must leave the position open.
        return position

    async def _submit_decision(
        self, decision_id: str, instrument: str, instrument_token: str,
        quantity: int, transaction_type: str, price: float,
    ) -> None:
        """Builds the same Decision shape DecisionEngine publishes for an
        automated TRADE, so RiskEngine and ExecutionEngine treat a manual
        order identically to an algo-generated one.
        """
        await event_bus.publish("DECISION_CREATED", {
            "decision_id": decision_id,
            "instrument": instrument,
            "instrument_token": instrument_token,
            "action": "TRADE",
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": "MARKET",
            "product": "I",
            "price": price,
            "timestamp": datetime.now(),
            "reasoning": "Manual order",
            "source": "MANUAL_TRADING",
        })

    async def _on_risk_decision(self, risk_dec: Dict[str, Any]) -> None:
        """Only rejections need handling here — an approval still has to
        wait for EXECUTION_UPDATE before a position can be trusted as OPEN,
        so approvals are a no-op at this stage.
        """
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
                position.closed_at = datetime.now()
            await self._publish_positions()
        elif decision_id in self._pending_pyramids:
            self._pending_pyramids.pop(decision_id)
            logger.warning(f"Manual trading: pyramid add rejected by risk: {reason}")
        elif decision_id in self._pending_exits:
            position_id = self._pending_exits.pop(decision_id)
            position = self.positions.get(position_id)
            if position:
                # Exit was rejected — clear the tentative exit_reason so the
                # still-open position doesn't display a stale close reason.
                position.exit_reason = None
            logger.warning(f"Manual trading: position close rejected by risk: {reason}")
            await self._publish_positions()

    async def _on_execution_update(self, exec_update: Dict[str, Any]) -> None:
        decision_id = exec_update.get("decision_id")
        status = exec_update.get("status")  # SUBMITTED | DRY_RUN | REJECTED | ERROR
        confirmed = status in CONFIRMED_STATUSES

        if decision_id in self._pending_entries:
            position_id = self._pending_entries.pop(decision_id)
            position = self.positions.get(position_id)
            if position is None:
                return
            if confirmed:
                position.status = "OPEN"
            else:
                position.status = "CLOSED"
                position.exit_reason = f"ENTRY_{status}"
                position.closed_at = datetime.now()
            await self._publish_positions()

        elif decision_id in self._pending_pyramids:
            pending = self._pending_pyramids.pop(decision_id)
            position = self.positions.get(pending["position_id"])
            if position is None:
                return
            if confirmed:
                position.entry_price = compute_weighted_entry_price(
                    position.quantity, position.entry_price,
                    pending["add_qty"], pending["add_price"],
                )
                position.quantity += pending["add_qty"]
                position.lots += pending["add_lots"]
                position.last_ltp = pending["add_price"]
            else:
                logger.warning(f"Manual trading: pyramid add failed at execution: {status}")
            await self._publish_positions()

        elif decision_id in self._pending_exits:
            position_id = self._pending_exits.pop(decision_id)
            position = self.positions.get(position_id)
            if position is None:
                return
            if confirmed:
                position.status = "CLOSED"
                position.closed_at = datetime.now()
                # exit_reason already set by close_position()
            else:
                logger.warning(f"Manual trading: position close failed at execution: {status}")
                position.exit_reason = None  # still OPEN, clear the tentative reason
            await self._publish_positions()

    async def _publish_positions(self) -> None:
        await event_bus.publish("manual_trading", {
            "positions": [p.model_dump(mode="json") for p in self.positions.values()],
        })

    async def _monitor_loop(self):
        while self.running:
            try:
                open_positions = [p for p in self.positions.values() if p.status == "OPEN"]
                if open_positions:
                    token = upstox_auth.load_token()
                    if token:
                        await self._check_positions(open_positions, token)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in ManualTradingEngine monitor loop: {exc}")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _check_positions(self, open_positions: List[ManualPosition], token: str) -> None:
        # Group by (underlying, expiry_date) so positions sharing a chain
        # share one fetch rather than each polling the API separately.
        groups: Dict[tuple, List[ManualPosition]] = {}
        for p in open_positions:
            groups.setdefault((p.underlying, p.expiry_date), []).append(p)

        for (underlying, expiry_date), positions in groups.items():
            try:
                chain = await self._fetch_chain(underlying, expiry_date, token)
            except ManualTradingError as exc:
                logger.warning(f"Manual trading monitor: chain fetch failed: {exc}")
                continue

            for position in positions:
                row = resolve_strike_row(chain, position.strike)
                if row is None:
                    continue
                leg = extract_leg(row, position.option_type)
                ltp = leg["market_data"]["ltp"]
                position.last_ltp = ltp

                reason = should_exit(ltp, position.stop_loss, position.target)
                if reason:
                    try:
                        await self.close_position(position.position_id, reason=reason)
                    except ManualTradingError as exc:
                        logger.error(f"Manual trading monitor: auto-close failed: {exc}")

        await self._publish_positions()


manual_trading_engine = ManualTradingEngine()
