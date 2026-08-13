from pydantic import BaseModel
from typing import Dict, Any
from datetime import datetime
from ..core.event_bus import event_bus

class RiskDecision(BaseModel):
    risk_id: str
    decision_id: str
    approved: bool
    timestamp: datetime
    reason: str

class RiskEngine:
    def __init__(self):
        pass

    def start(self):
        event_bus.subscribe("DECISION_CREATED", self.process_decision)

    async def process_decision(self, dec_data: Dict[str, Any]):
        approved = dec_data['action'] == "TRADE"
        risk_dec = RiskDecision(
            risk_id=f"RISK_{dec_data['decision_id']}",
            decision_id=dec_data['decision_id'],
            approved=approved,
            timestamp=dec_data['timestamp'],
            reason="Passed risk checks" if approved else "Action is not TRADE"
        )
        await event_bus.publish("RISK_DECISION", risk_dec.model_dump())

        if approved:
            await event_bus.publish("EXECUTION_REQUEST", {
                "instrument": dec_data['instrument'],
                "decision_id": dec_data['decision_id'],
                "timestamp": dec_data['timestamp']
            })
