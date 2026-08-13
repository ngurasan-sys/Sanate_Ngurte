from pydantic import BaseModel
from typing import List, Dict
from datetime import datetime
from ..core.event_bus import event_bus

class Opportunity(BaseModel):
    opportunity_id: str
    instrument: str
    timestamp: datetime
    direction: str
    confidence: float
    evidence: str
    source_signals: List[str]

class OpportunityEngine:
    def __init__(self):
        self.opportunities: List[Opportunity] = []

    def start(self):
        event_bus.subscribe("STRATEGY_SIGNAL", self.process_signal)

    async def process_signal(self, signal: Dict):
        opp = Opportunity(
            opportunity_id=f"OPP_{signal['signal_id']}",
            instrument=signal['instrument'],
            timestamp=signal['timestamp'],
            direction=signal['direction'],
            confidence=signal['confidence'],
            evidence=f"Derived from strategy {signal['strategy_id']}",
            source_signals=[signal['signal_id']]
        )
        # Prevent indefinite memory leak
        if len(self.opportunities) > 1000:
            self.opportunities.pop(0)
        self.opportunities.append(opp)
        await event_bus.publish("OPPORTUNITY_CREATED", opp.model_dump())
