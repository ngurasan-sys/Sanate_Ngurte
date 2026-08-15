import logging
from datetime import datetime
from typing import Any, Dict

from backend.app.core.event_bus import event_bus
from backend.app.execution.order_gateway import (
    ExecutionMode,
    OrderRequest,
    order_gateway,
    resolve_mode,
)

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """The execution boundary — the only consumer of EXECUTION_REQUEST.

    This now actually calls the broker via OrderGateway, but the gateway
    defaults to DRY_RUN: nothing reaches a real broker unless the
    execution mode has been deliberately configured (see order_gateway
    for the two-switch LIVE arming).

    It never claims an order was submitted unless the broker returned a
    real order_id.
    """

    def __init__(self):
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        event_bus.subscribe("EXECUTION_REQUEST", self.execute_order)
        self._started = True
        logger.info("Execution engine started (mode: %s).", resolve_mode().value)

    def stop(self) -> None:
        self._started = False
        logger.info("Execution engine stopped.")

    async def execute_order(self, req_data: Dict[str, Any]) -> None:
        instrument = req_data.get("instrument")
        instrument_token = req_data.get("instrument_token")
        decision_id = req_data.get("decision_id")
        quantity = int(req_data.get("quantity", 0) or 0)
        price = float(req_data.get("price", 0.0) or 0.0)
        source = req_data.get("source")

        if not instrument_token:
            detail = (
                f"No instrument_token on the execution request for {instrument!r} — "
                "cannot place an order without the broker's instrument key."
            )
            logger.error(detail)
            await self._publish_update(
                instrument, instrument_token, decision_id, "REJECTED", resolve_mode(),
                quantity=quantity, price=price, source=source, detail=detail,
            )
            return

        request = OrderRequest(
            instrument_token=instrument_token,
            transaction_type=req_data.get("transaction_type", "BUY"),
            quantity=quantity,
            order_type=req_data.get("order_type", "MARKET"),
            product=req_data.get("product", "I"),
            price=price,
            tag=f"dec_{decision_id}" if decision_id else None,
        )

        result = await order_gateway.place_order(request)

        await self._publish_update(
            instrument,
            instrument_token,
            decision_id,
            result.status,
            result.mode,
            quantity=quantity,
            price=price,
            source=source,
            order_id=result.order_id,
            detail=result.detail,
        )

    async def _publish_update(
        self, instrument, instrument_token, decision_id, status: str, mode: ExecutionMode,
        quantity: int = 0, price: float = 0.0, source: str = None,
        order_id=None, detail=None,
    ) -> None:
        await event_bus.publish("EXECUTION_UPDATE", {
            "instrument": instrument,
            "instrument_token": instrument_token,
            "decision_id": decision_id,
            "status": status,
            "mode": mode.value,
            "quantity": quantity,
            "price": price,
            "source": source,
            "order_id": order_id,
            "detail": detail,
            "timestamp": datetime.now().isoformat(),
        })


execution_engine = ExecutionEngine()
