import logging
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime
from ..core.event_bus import event_bus

logger = logging.getLogger(__name__)


class Opportunity(BaseModel):
    opportunity_id: str
    instrument: str
    timestamp: datetime
    direction: str
    confidence: float
    evidence: str
    source_signals: List[str]


# Strategies that emit a CE/PE-style `action` instead of a `direction` field
# (gap_opening, atr) — direction is recoverable from that, not fabricated.
_ACTION_DIRECTION_MAP = {"CE": "CALL", "PE": "PUT"}


def _infer_direction(signal: Dict) -> Optional[str]:
    direction = signal.get("direction")
    if direction:
        return direction

    action = signal.get("action", "")
    for token, direction in _ACTION_DIRECTION_MAP.items():
        if token in action:
            return direction
    return None


class OpportunityEngine:
    """Bridges STRATEGY_SIGNAL (per-strategy, inconsistent shape) into
    OPPORTUNITY_CREATED (the uniform shape decision/risk/execution expect).

    Not every strategy's signal is convertible: gap_opening and atr publish
    `symbol`/`underlying`/`action` with no `confidence` field at all — their
    sizing logic runs on lots/tiers/regime, not a confidence score, so there
    is no honest number to put in Opportunity.confidence. Those signals are
    logged and dropped rather than assigned a fabricated confidence, since
    DecisionEngine's TRADE/WAIT call is a confidence threshold — a made-up
    number there would silently misrepresent the strategy's own conviction.
    """

    def __init__(self):
        self.opportunities: List[Opportunity] = []

    def start(self):
        event_bus.subscribe("STRATEGY_SIGNAL", self.process_signal)

    async def process_signal(self, signal: Dict):
        signal_id = signal.get("signal_id")
        strategy_id = signal.get("strategy_id")
        instrument = signal.get("instrument") or signal.get("symbol")
        direction = _infer_direction(signal)
        confidence = signal.get("confidence")
        timestamp = signal.get("timestamp")

        missing = [
            name for name, value in (
                ("signal_id", signal_id), ("strategy_id", strategy_id),
                ("instrument", instrument), ("direction", direction),
                ("confidence", confidence), ("timestamp", timestamp),
            ) if value is None
        ]
        if missing:
            logger.warning(
                "Dropping STRATEGY_SIGNAL from %s: missing %s — this "
                "strategy's signal shape isn't convertible to an "
                "Opportunity without fabricating a value.",
                strategy_id or "<unknown strategy>", missing,
            )
            return

        opp = Opportunity(
            opportunity_id=f"OPP_{signal_id}",
            instrument=instrument,
            timestamp=timestamp,
            direction=direction,
            confidence=confidence,
            evidence=f"Derived from strategy {strategy_id}",
            source_signals=[signal_id],
        )
        # Prevent indefinite memory leak
        if len(self.opportunities) >= 1000:
            self.opportunities.pop(0)
        self.opportunities.append(opp)
        await event_bus.publish("OPPORTUNITY_CREATED", opp.model_dump())


opportunity_engine = OpportunityEngine()
