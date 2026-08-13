import logging
from backend.app.core.event_bus import event_bus

logger = logging.getLogger(__name__)

class ExecutionEngine:
    def __init__(self):
        event_bus.subscribe("risk_passed", self.execute_order)

    async def execute_order(self, decision: dict):
        instrument = decision.get("instrument")
        action = decision.get("action")
        logger.info(f"Execution engine executing {action} for {instrument}")

        execution_result = {
            "instrument": instrument,
            "status": "SUBMITTED",
            "action": action
        }
        event_bus.publish("execution_update", execution_result)
        event_bus.publish("persist_execution", execution_result)

execution_engine = ExecutionEngine()
