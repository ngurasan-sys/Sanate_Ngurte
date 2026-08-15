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
                      REAL MONEY MOVES. Requires UPSTOX_EXECUTION_MODE
                      to be set to exactly "LIVE" *and* a separate
                      confirmation flag, so a single stray env var
                      cannot arm live trading by itself.

An order is only ever reported as SUBMITTED when the broker actually
returned an order_id. Every other outcome reports what really happened.
"""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

import httpx

from backend.app.core import upstox_auth

logger = logging.getLogger(__name__)

LIVE_ORDER_URL = "https://api-hft.upstox.com/v2/order/place"
SANDBOX_ORDER_URL = "https://api-sandbox.upstox.com/v2/order/place"


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
    """LIVE requires BOTH UPSTOX_EXECUTION_MODE=LIVE and
    UPSTOX_LIVE_TRADING_CONFIRMED=YES. Two independent switches, so no
    single misconfigured variable can silently arm real trading.
    """
    raw = (os.environ.get("UPSTOX_EXECUTION_MODE") or "DRY_RUN").strip().upper()

    try:
        mode = ExecutionMode(raw)
    except ValueError:
        logger.warning(
            "Unrecognised UPSTOX_EXECUTION_MODE=%r — falling back to DRY_RUN.", raw
        )
        return ExecutionMode.DRY_RUN

    if mode is ExecutionMode.LIVE:
        confirmed = (os.environ.get("UPSTOX_LIVE_TRADING_CONFIRMED") or "").strip().upper()
        if confirmed != "YES":
            logger.error(
                "UPSTOX_EXECUTION_MODE=LIVE but UPSTOX_LIVE_TRADING_CONFIRMED is not 'YES'. "
                "Refusing to arm live trading; falling back to DRY_RUN."
            )
            return ExecutionMode.DRY_RUN

    return mode


def _resolve_token(mode: ExecutionMode) -> Optional[str]:
    """Sandbox uses its own token (Upstox issues a separate sandbox-only
    token that cannot place live orders, and vice versa)."""
    if mode is ExecutionMode.SANDBOX:
        return os.environ.get("UPSTOX_SANDBOX_ACCESS_TOKEN")
    return upstox_auth.load_token()


class OrderGateway:
    def __init__(self):
        self.last_result: Optional[OrderResult] = None

    async def place_order(self, request: OrderRequest) -> OrderResult:
        mode = resolve_mode()
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

        token = _resolve_token(mode)
        if not token:
            detail = (
                "No sandbox access token (set UPSTOX_SANDBOX_ACCESS_TOKEN)."
                if mode is ExecutionMode.SANDBOX
                else "No saved Upstox token — log in via /api/v1/broker/upstox/login."
            )
            logger.error("Order rejected before submission: %s", detail)
            result = OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)
            self.last_result = result
            return result

        url = SANDBOX_ORDER_URL if mode is ExecutionMode.SANDBOX else LIVE_ORDER_URL

        if mode is ExecutionMode.LIVE:
            logger.warning(
                "PLACING A REAL LIVE ORDER (real money): %s %s x%s",
                request.transaction_type, request.instrument_token, request.quantity,
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            # A transport failure means we do NOT know whether the broker
            # received the order. Never report this as submitted.
            detail = f"Order request failed in transport: {exc}. Order status UNKNOWN — verify manually."
            logger.error(detail)
            result = OrderResult(status="ERROR", mode=mode, payload=payload, detail=detail)
            self.last_result = result
            return result

        if response.status_code != 200:
            detail = f"Broker rejected order ({response.status_code}): {response.text}"
            logger.error(detail)
            result = OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)
            self.last_result = result
            return result

        body = response.json()
        order_id = (body.get("data") or {}).get("order_id")
        if not order_id:
            detail = f"Broker returned 200 but no order_id: {body}. Order status UNKNOWN — verify manually."
            logger.error(detail)
            result = OrderResult(status="ERROR", mode=mode, payload=payload, detail=detail)
            self.last_result = result
            return result

        logger.info("Order accepted by broker (%s mode). order_id=%s", mode.value, order_id)
        result = OrderResult(
            status="SUBMITTED", mode=mode, order_id=order_id, payload=payload,
            detail="Broker returned an order_id.",
        )
        self.last_result = result
        return result


order_gateway = OrderGateway()
