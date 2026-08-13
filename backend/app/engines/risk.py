import logging
from backend.app.core.event_bus import event_bus
from backend.app.core.state import market_state

logger = logging.getLogger(__name__)

class RiskEngine:
    def __init__(self):
        event_bus.subscribe("decision_created", self.evaluate_risk)

    async def evaluate_risk(self, decision: dict):
        instrument = decision.get("instrument")
        action = decision.get("action")
        logger.info(f"Risk engine evaluating {action} for {instrument}")

        risk_passed = True

        if risk_passed:
            event_bus.publish("risk_passed", decision)
            event_bus.publish("persist_risk_event", {"decision": decision, "status": "passed"})
        else:
            event_bus.publish("risk_failed", decision)
            event_bus.publish("persist_risk_event", {"decision": decision, "status": "failed"})

risk_engine = RiskEngine()
