"""Dhan's BrokerExecutionAdapter implementation. Dhan has no separate
sandbox environment (unlike Upstox) — SANDBOX mode is honestly rejected
here rather than silently routed to LIVE.
"""

import logging

import httpx

from backend.app.core import dhan_auth
from backend.app.execution.order_gateway import ExecutionMode, OrderRequest, OrderResult

logger = logging.getLogger(__name__)

DHAN_ORDER_URL = "https://api.dhan.co/v2/orders"

PRODUCT_MAP = {"I": "INTRADAY", "D": "CNC", "MTF": "MTF"}
ORDER_TYPE_MAP = {"MARKET": "MARKET", "LIMIT": "LIMIT", "SL": "STOP_LOSS", "SL-M": "STOP_LOSS_MARKET"}


class DhanExecutionAdapter:
    async def place_order(self, request: OrderRequest, mode: ExecutionMode) -> OrderResult:
        payload = request.to_payload()

        if mode is ExecutionMode.SANDBOX:
            detail = "Dhan has no sandbox environment — use DRY_RUN to test, or LIVE to place a real order."
            logger.error("Order rejected before submission: %s", detail)
            return OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)

        token = dhan_auth.load_token()
        client_id = dhan_auth.load_client_id()
        if not token or not client_id:
            detail = "No saved Dhan token/client ID — connect Dhan via the Broker Connections page."
            logger.error("Order rejected before submission: %s", detail)
            return OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)

        body = {
            "dhanClientId": client_id,
            "transactionType": request.transaction_type,
            "exchangeSegment": "NSE_FNO",
            "productType": PRODUCT_MAP.get(request.product, "INTRADAY"),
            "orderType": ORDER_TYPE_MAP.get(request.order_type, "MARKET"),
            "validity": request.validity,
            "securityId": request.instrument_token,
            "quantity": request.quantity,
            "price": request.price,
            "triggerPrice": request.trigger_price,
            "disclosedQuantity": request.disclosed_quantity,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    DHAN_ORDER_URL, json=body,
                    headers={"access-token": token, "Content-Type": "application/json", "Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            detail = f"Order request failed in transport: {exc}. Order status UNKNOWN — verify manually."
            logger.error(detail)
            return OrderResult(status="ERROR", mode=mode, payload=payload, detail=detail)

        if response.status_code not in (200, 201):
            detail = f"Dhan rejected order ({response.status_code}): {response.text}"
            logger.error(detail)
            return OrderResult(status="REJECTED", mode=mode, payload=payload, detail=detail)

        resp_body = response.json()
        order_id = resp_body.get("orderId")
        if not order_id:
            detail = f"Dhan returned {response.status_code} but no orderId: {resp_body}. Order status UNKNOWN — verify manually."
            logger.error(detail)
            return OrderResult(status="ERROR", mode=mode, payload=payload, detail=detail)

        logger.info("Order accepted by Dhan (%s mode). order_id=%s", mode.value, order_id)
        return OrderResult(status="SUBMITTED", mode=mode, order_id=order_id, payload=payload, detail="Dhan returned an orderId.")


dhan_execution_adapter = DhanExecutionAdapter()
