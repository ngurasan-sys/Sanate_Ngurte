"""Upstox's BrokerExecutionAdapter implementation — the actual
network-calling order-placement logic, moved out of order_gateway.py
unchanged. order_gateway.OrderGateway.place_order still owns the DRY_RUN
short-circuit and the two-factor LIVE arm check (resolve_mode()); this
adapter is only ever reached for SANDBOX/LIVE.
"""

import logging
from typing import Optional

import httpx

from backend.app.core import upstox_auth
from backend.app.execution.order_gateway import ExecutionMode, OrderRequest, OrderResult

logger = logging.getLogger(__name__)

LIVE_ORDER_URL = "https://api-hft.upstox.com/v2/order/place"
SANDBOX_ORDER_URL = "https://api-sandbox.upstox.com/v2/order/place"


def _resolve_token(mode: ExecutionMode) -> Optional[str]:
    """Sandbox uses its own token (Upstox issues a separate sandbox-only
    token that cannot place live orders, and vice versa)."""
    if mode is ExecutionMode.SANDBOX:
        import os
        return os.environ.get("UPSTOX_SANDBOX_ACCESS_TOKEN")
    return upstox_auth.load_token()


class UpstoxExecutionAdapter:
    async def place_order(self, request: OrderRequest, mode: ExecutionMode) -> OrderResult:
        payload = request.to_payload()

        token = _resolve_token(mode)
        if not token:
            detail = (
                "No sandbox access token (set UPSTOX_SANDBOX_ACCESS_TOKEN)."
                if mode is ExecutionMode.SANDBOX
                else "No saved Upstox token — log in via /api/v1/brokers/upstox/login."
            )
            logger.error("Order rejected before submission: %s", detail)
            return OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)

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
            detail = f"Order request failed in transport: {exc}. Order status UNKNOWN — verify manually."
            logger.error(detail)
            return OrderResult(status="ERROR", mode=mode, payload=payload, detail=detail)

        if response.status_code != 200:
            detail = f"Broker rejected order ({response.status_code}): {response.text}"
            logger.error(detail)
            return OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)

        body = response.json()
        order_id = (body.get("data") or {}).get("order_id")
        if not order_id:
            detail = f"Broker returned 200 but no order_id: {body}. Order status UNKNOWN — verify manually."
            logger.error(detail)
            return OrderResult(status="ERROR", mode=mode, payload=payload, detail=detail)

        logger.info("Order accepted by broker (%s mode). order_id=%s", mode.value, order_id)
        return OrderResult(
            status="SUBMITTED", mode=mode, order_id=order_id, payload=payload,
            detail="Broker returned an order_id.",
        )


upstox_execution_adapter = UpstoxExecutionAdapter()
