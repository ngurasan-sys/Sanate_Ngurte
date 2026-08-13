import logging
from datetime import datetime
from typing import Any, Dict

from backend.app.core.event_bus import event_bus


logger = logging.getLogger(__name__)


class ExecutionEngine:
    def __init__(self):
        self._started = False

    def start(self) -> None:
        """
        Start the execution engine and subscribe to
        approved execution requests.
        """

        if self._started:
            return

        event_bus.subscribe(
            "EXECUTION_REQUEST",
            self.execute_order,
        )

        self._started = True

        logger.info("Execution engine started.")

    async def execute_order(
        self,
        req_data: Dict[str, Any],
    ) -> None:
        """
        Process an approved execution request.

        This layer currently represents the execution boundary.
        It must not claim an order was filled unless an actual
        broker execution confirmation is received.
        """

        instrument = req_data.get("instrument")
        decision_id = req_data.get("decision_id")
        action = req_data.get("action")

        logger.info(
            "Execution request received for %s",
            instrument,
        )

        result = {
            "instrument": instrument,
            "status": "SUBMITTED",
            "action": action,
            "timestamp": datetime.now(),
            "decision_id": decision_id,
        }

        await event_bus.publish(
            "EXECUTION_UPDATE",
            result,
        )


execution_engine = ExecutionEngine()