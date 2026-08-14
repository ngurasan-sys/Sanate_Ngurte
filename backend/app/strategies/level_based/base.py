from typing import Dict, Any, Optional
from datetime import datetime
from ...core.event_bus import event_bus

class BaseLevelStrategy:
    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id

    async def evaluate(self, tick: Dict[str, Any], levels: list):
        raise NotImplementedError

    async def emit_signal(self, instrument: str, direction: str, level_id: str, confidence: float, evidence: str):
        signal = {
            "signal_id": f"SIG_{self.strategy_id}_{datetime.now().timestamp()}",
            "strategy_id": self.strategy_id,
            "instrument": instrument,
            "timestamp": datetime.now(),
            "direction": direction,
            "level_id": level_id,
            "confidence": confidence,
            "evidence": evidence
        }
        await event_bus.publish("STRATEGY_SIGNAL", signal)
