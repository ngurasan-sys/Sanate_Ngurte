import logging
from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel

from backend.app.core.event_bus import event_bus
from backend.app.engines.algo_config import algo_config_state
from backend.app.execution.order_gateway import ExecutionMode, resolve_mode
from backend.app.execution.risk_limits import (
    RiskLimits,
    RiskState,
    check_cas_enabled,
    check_ofao_enabled,
    evaluate_algo_extra,
    evaluate_all,
)
from backend.app.order_flow.footprint_processor import footprint_processor
from backend.app.strategies.cas_dislocation.config_state import cas_config_state
from backend.app.strategies.order_flow_absorption.engine import ofao_engine

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

        The algo capital budget follows the same real-submission-only rule
        (DRY_RUN never spends real capital). The pyramid tier counter is
        looser on purpose: it advances on DRY_RUN too, so tier progression
        is actually testable without needing EXECUTION_MODE=LIVE.
        """
        status = exec_data.get("status")
        if status == "SUBMITTED":
            self.state.orders_placed_today += 1

        if exec_data.get("source") != "ALGO":
            return

        if status == "SUBMITTED":
            self.state.capital_deployed_today += (
                exec_data.get("quantity", 0) * exec_data.get("price", 0.0)
            )
        if status in ("SUBMITTED", "DRY_RUN"):
            instrument_key = exec_data.get("instrument_token")
            if instrument_key:
                self.state.fill_count_by_instrument[instrument_key] = (
                    self.state.fill_count_by_instrument.get(instrument_key, 0) + 1
                )

    async def process_decision(self, dec_data: Dict[str, Any]):
        decision_id = dec_data.get("decision_id", "UNKNOWN")

        if dec_data.get("action") != "TRADE":
            await self._publish(decision_id, dec_data, False, "Action is not TRADE.")
            return

        quantity = int(dec_data.get("quantity", 0) or 0)
        price = float(dec_data.get("price", 0.0) or 0.0)
        instrument = dec_data.get("instrument", "")
        instrument_token = dec_data.get("instrument_token", "")
        source = dec_data.get("source", "ALGO")
        now = datetime.now().time()

        approved, reasons = evaluate_all(self.limits, self.state, quantity, now)

        # Manual trading orders carry their own per-order sizing already —
        # the algo capital budget and pyramid schedule apply only to
        # ALGO-sourced decisions (see risk_limits.evaluate_algo_extra).
        if source == "ALGO":
            algo_approved, algo_reasons = evaluate_algo_extra(
                algo_config_state.get(), self.state, instrument, instrument_token, quantity, price,
            )
            approved = approved and algo_approved
            reasons = reasons + algo_reasons
        elif source == "CAS_DISLOCATION":
            cas_reason = check_cas_enabled(cas_config_state.get())
            if cas_reason:
                approved = False
                reasons = reasons + [cas_reason]
        elif source == "OFAO":
            ofao_reason = check_ofao_enabled(ofao_engine.config)
            if ofao_reason:
                approved = False
                reasons = reasons + [ofao_reason]
            # Hard data-provenance gate: OFAOEngine itself never knows or
            # branches on real-vs-mock ticks (spec §35 forbids that), so
            # this is the ONE place in the whole pipeline where a mock
            # footprint feed is prevented from ever reaching a real order.
            # DRY_RUN/SANDBOX stay unaffected — this only blocks the LIVE
            # path, and only for OFAO specifically.
            elif resolve_mode() is ExecutionMode.LIVE and footprint_processor.data_source != "REAL":
                approved = False
                reasons = reasons + [
                    "OFAO LIVE = BLOCKED: underlying footprint data source is "
                    f"{footprint_processor.data_source} (mock feed), not REAL. "
                    "No real Level-2 futures feed is wired in yet."
                ]

        reason_text = "Passed all risk checks." if approved else " ".join(reasons)

        await self._publish(decision_id, dec_data, approved, reason_text)

        if approved:
            await event_bus.publish("EXECUTION_REQUEST", {
                "instrument": instrument,
                "instrument_token": instrument_token,
                "transaction_type": dec_data.get("transaction_type", "BUY"),
                "quantity": quantity,
                "order_type": dec_data.get("order_type", "MARKET"),
                "product": dec_data.get("product", "I"),
                "price": price,
                "decision_id": decision_id,
                "timestamp": dec_data.get("timestamp"),
                "source": source,
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
