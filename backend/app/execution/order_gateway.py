"""Real Upstox order placement gateway.

SAFETY MODEL — read before changing anything here.

This module is the only place in the codebase that can send a real,
money-moving order to a broker. It therefore defaults to doing nothing
of the kind:

  DRY_RUN  (default)  Builds and logs the exact payload that *would* be
                      sent. Makes no network call at all. This is what
                      you get unless someone deliberately configures
                      otherwise.
  SANDBOX             Sends to Upstox's sandbox host using a separate
                      sandbox token. No real money, no real position.
  LIVE                Sends to the real HFT host with the real token.
                      REAL MONEY MOVES. Requires EXECUTION_MODE
                      to be set to exactly "LIVE" *and* a second,
                      independent confirmation: either
                      LIVE_TRADING_CONFIRMED=YES in the
                      environment, or the runtime arm switch toggled
                      from the frontend's execution-control panel
                      (backend.app.execution.runtime_state). The
                      runtime switch always resets to disarmed on
                      process restart. Either switch alone is not
                      enough — a single stray env var or a forgotten
                      UI toggle cannot arm live trading by itself.

An order is only ever reported as SUBMITTED when the broker actually
returned an order_id. Every other outcome reports what really happened.
"""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from backend.app.core.active_broker import active_broker
from backend.app.execution.runtime_state import execution_runtime_state

logger = logging.getLogger(__name__)


class ExecutionMode(str, Enum):
    DRY_RUN = "DRY_RUN"
    SANDBOX = "SANDBOX"
    LIVE = "LIVE"


class OrderRejected(Exception):
    """Raised when an order is refused before ever reaching the broker."""


@dataclass
class OrderRequest:
    instrument_token: str
    transaction_type: str  # BUY | SELL
    quantity: int
    order_type: str = "MARKET"  # MARKET | LIMIT | SL | SL-M
    product: str = "I"          # I=Intraday, D=Delivery, MTF
    validity: str = "DAY"       # DAY | IOC
    price: float = 0.0
    trigger_price: float = 0.0
    disclosed_quantity: int = 0
    tag: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "quantity": self.quantity,
            "product": self.product,
            "validity": self.validity,
            "price": self.price,
            "instrument_token": self.instrument_token,
            "order_type": self.order_type,
            "transaction_type": self.transaction_type,
            "disclosed_quantity": self.disclosed_quantity,
            "trigger_price": self.trigger_price,
        }
        if self.tag:
            payload["tag"] = self.tag
        return payload


@dataclass
class OrderResult:
    status: str  # SUBMITTED | DRY_RUN | REJECTED | ERROR
    mode: ExecutionMode
    order_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    detail: Optional[str] = None

    @property
    def is_real_submission(self) -> bool:
        """True only when a broker actually accepted the order and gave
        us an order_id. DRY_RUN is never a real submission."""
        return self.status == "SUBMITTED" and self.order_id is not None


def resolve_mode() -> ExecutionMode:
    """LIVE requires EXECUTION_MODE=LIVE AND a second, independent
    confirmation — either LIVE_TRADING_CONFIRMED=YES in the
    environment, or the runtime arm switch armed via the frontend's
    execution-control panel. Two independent switches, so no single
    misconfigured variable or forgotten toggle can silently arm real
    trading.
    """
    raw = (os.environ.get("EXECUTION_MODE") or "DRY_RUN").strip().upper()

    try:
        mode = ExecutionMode(raw)
    except ValueError:
        logger.warning(
            "Unrecognised EXECUTION_MODE=%r — falling back to DRY_RUN.", raw
        )
        return ExecutionMode.DRY_RUN

    if mode is ExecutionMode.LIVE:
        confirmed = (os.environ.get("LIVE_TRADING_CONFIRMED") or "").strip().upper()
        if confirmed != "YES" and not execution_runtime_state.is_armed():
            logger.error(
                "EXECUTION_MODE=LIVE but neither LIVE_TRADING_CONFIRMED=YES "
                "nor the runtime arm switch is set. Refusing to arm live trading; "
                "falling back to DRY_RUN."
            )
            return ExecutionMode.DRY_RUN

    return mode


class OrderGateway:
    def __init__(self):
        self.last_result: Optional[OrderResult] = None

    async def place_order(self, request: OrderRequest, *, force_dry_run: bool = False) -> OrderResult:
        mode = ExecutionMode.DRY_RUN if force_dry_run else resolve_mode()
        payload = request.to_payload()

        if mode is ExecutionMode.DRY_RUN:
            logger.info(
                "[DRY_RUN] Would place order (no network call made): %s", payload
            )
            result = OrderResult(
                status="DRY_RUN", mode=mode, payload=payload,
                detail="DRY_RUN mode — no order was sent to any broker.",
            )
            self.last_result = result
            return result

        adapter = active_broker.get_active_execution_adapter()
        if adapter is None:
            detail = "No active broker — connect and activate a broker before placing real orders."
            logger.error("Order rejected before submission: %s", detail)
            result = OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)
            self.last_result = result
            return result

        result = await adapter.place_order(request, mode)
        self.last_result = result
        return result


order_gateway = OrderGateway()
