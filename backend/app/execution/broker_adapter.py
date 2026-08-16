"""Broker-agnostic order-execution interface every broker's execution
client implements — Upstox today, Dhan/Zerodha in later phases.
order_gateway.OrderGateway dispatches to whichever broker is active via
backend.app.core.active_broker.get_active_execution_adapter(); it never
imports a specific broker's execution module directly.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from backend.app.execution.order_gateway import ExecutionMode, OrderRequest, OrderResult


@runtime_checkable
class BrokerExecutionAdapter(Protocol):
    async def place_order(self, request: "OrderRequest", mode: "ExecutionMode") -> "OrderResult":
        """Place a real order (SANDBOX or LIVE mode only — DRY_RUN is
        handled entirely inside OrderGateway and never reaches an
        adapter). Must never report status="SUBMITTED" unless the broker
        actually returned an order_id."""
        ...
