import logging
from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel

from backend.app.core.event_bus import event_bus
from backend.app.execution.risk_limits import (
    RiskLimits,
    RiskState,
    evaluate_all,
)

logger = logging.getLogger(__name__)


class RiskDecision(BaseModel):
    risk_id: str
    decision_id: str
    approved: bool
    timestamp: datetime
    reason: str


class RiskEngine:
    """Real pre-trade risk gate.

    Previously this approved anything whose action happened to be
    "TRADE". It now runs actual limit checks (kill switch, market hours,
    quantity, open positions, daily loss, daily order count) and only
    forwards an EXECUTION_REQUEST when every one of them passes.
    """

    def __init__(self, limits: RiskLimits = None):
        self.limits = limits or RiskLimits()
        self.state = RiskState()
        self._started = False

    def start(self):
        if self._started:
            return
        event_bus.subscribe("DECISION_CREATED", self.process_decision)
        event_bus.subscribe("EXECUTION_UPDATE", self.record_execution)
        self._started = True
        logger.info("Risk engine started with real limit checks: %s", self.limits)

    def stop(self):
        self._started = False
        logger.info("Risk engine stopped")

    def halt(self, reason: str):
        """Trip the halt switch — every subsequent decision is rejected
        until this is cleared."""
        self.state.halted_reason = reason
        logger.warning("Risk engine HALTED: %s", reason)

    def resume(self):
        self.state.halted_reason = None
        logger.info("Risk engine halt cleared")

    async def record_execution(self, exec_data: Dict[str, Any]):
        """Count only real broker submissions against the daily order cap.
        A DRY_RUN or rejected order must not consume the day's budget.
        """
        if exec_data.get("status") == "SUBMITTED":
            self.state.orders_placed_today += 1

    async def process_decision(self, dec_data: Dict[str, Any]):
        decision_id = dec_data.get("decision_id", "UNKNOWN")

        if dec_data.get("action") != "TRADE":
            await self._publish(decision_id, dec_data, False, "Action is not TRADE.")
            return

        quantity = int(dec_data.get("quantity", 0) or 0)
        now = datetime.now().time()

        approved, reasons = evaluate_all(self.limits, self.state, quantity, now)
        reason_text = "Passed all risk checks." if approved else " ".join(reasons)

        await self._publish(decision_id, dec_data, approved, reason_text)

        if approved:
            await event_bus.publish("EXECUTION_REQUEST", {
                "instrument": dec_data.get("instrument"),
                "instrument_token": dec_data.get("instrument_token"),
                "transaction_type": dec_data.get("transaction_type", "BUY"),
                "quantity": quantity,
                "order_type": dec_data.get("order_type", "MARKET"),
                "product": dec_data.get("product", "I"),
                "price": dec_data.get("price", 0.0),
                "decision_id": decision_id,
                "timestamp": dec_data.get("timestamp"),
            })
        else:
            logger.info("Risk REJECTED decision %s: %s", decision_id, reason_text)

    async def _publish(self, decision_id, dec_data, approved: bool, reason: str):
        risk_dec = RiskDecision(
            risk_id=f"RISK_{decision_id}",
            decision_id=decision_id,
            approved=approved,
            timestamp=dec_data.get("timestamp") or datetime.now(),
            reason=reason,
        )
        await event_bus.publish("RISK_DECISION", risk_dec.model_dump(mode="json"))


risk_engine = RiskEngine()
