from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
from backend.app.core.event_bus import event_bus

class Decision(BaseModel):
    decision_id: str
    opportunity_id: str
    instrument: str
    action: str
    timestamp: datetime
    reasoning: str
    # Distinguishes an automated decision from a manual_trading order
    # (which tags "MANUAL_TRADING" itself) — RiskEngine uses this to know
    # whether the algo capital budget/pyramid schedule apply at all.
    source: str = "ALGO"
    # Threaded through from Opportunity.strategy_id — lets RiskEngine gate
    # new entries per-strategy (strategy_runtime.is_strategy_permitted)
    # even though `source` itself is the shared generic "ALGO" tag for
    # every strategy that isn't CAS_DISLOCATION/OFAO/MANUAL_TRADING.
    strategy_id: Optional[str] = None

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
            reasoning=f"Confidence is {opp_data['confidence']}",
            strategy_id=opp_data.get('strategy_id'),
        )
        await event_bus.publish("DECISION_CREATED", decision.model_dump())

decision_engine = DecisionEngine()
