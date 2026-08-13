import logging
from backend.app.core.event_bus import event_bus
from backend.app.core.state import market_state

logger = logging.getLogger(__name__)

class DecisionEngine:
    def __init__(self):
        event_bus.subscribe("strategy_signal", self.evaluate_signal)

    async def evaluate_signal(self, event_data: dict):
        instrument = event_data.get("instrument")
        signal = event_data.get("signal")
        current_tick = market_state.get_latest_tick(instrument)

        if not current_tick:
            return

        logger.info(f"Decision engine evaluating signal for {instrument}")
        decision = {
            "instrument": instrument,
            "action": "BUY" if signal > 0 else "SELL",
            "price": current_tick.get("price"),
            "confidence": abs(signal)
        }
        event_bus.publish("decision_created", decision)

decision_engine = DecisionEngine()
