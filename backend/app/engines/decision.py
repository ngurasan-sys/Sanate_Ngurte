from pydantic import BaseModel
from typing import Dict, Any
from datetime import datetime
from backend.app.core.event_bus import event_bus

class Decision(BaseModel):
    decision_id: str
    opportunity_id: str
    instrument: str
    action: str
    timestamp: datetime
    reasoning: str

class DecisionEngine:
    def __init__(self):
        pass

    def start(self):
        event_bus.subscribe("OPPORTUNITY_CREATED", self.process_opportunity)

    async def process_opportunity(self, opp_data: Dict[str, Any]):
        decision = Decision(
            decision_id=f"DEC_{opp_data['opportunity_id']}",
            opportunity_id=opp_data['opportunity_id'],
            instrument=opp_data['instrument'],
            action="TRADE" if opp_data['confidence'] > 80 else "WAIT",
            timestamp=opp_data['timestamp'],
            reasoning=f"Confidence is {opp_data['confidence']}"
        )
        await event_bus.publish("DECISION_CREATED", decision.model_dump())

decision_engine = DecisionEngine()
