import asyncio
from typing import Dict, Any, Optional
import logging
from backend.app.core.event_bus import event_bus
from .engine import OrderFlowEngine
from .models import OrderFlowState

logger = logging.getLogger(__name__)

class OrderFlowTickProcessor:
    def __init__(self):
        self.engine = OrderFlowEngine()
        self.dirty_states: Dict[str, OrderFlowState] = {}
        self.broadcast_interval = 0.05  # 20Hz broadcast limit
        self._broadcast_task: Optional[asyncio.Task] = None

    def start(self):
        event_bus.subscribe("market_update", self.on_market_tick)
        event_bus.subscribe("greeks_update", self.on_greeks_update)
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        logger.info("OrderFlowTickProcessor started")

    async def on_market_tick(self, tick: Dict[str, Any]):
        state = self.engine.process_tick(tick)
        if state:
            self.dirty_states[state.instrument_key] = state

    async def on_greeks_update(self, update: Dict[str, Any]):
        # Inject Greeks into a synthetic tick for the engine
        tick = {
            "instrument_key": update.get("instrument_key"),
            "ltt": update.get("timestamp", 0),
            "greeks": update.get("greeks")
        }
        state = self.engine.process_tick(tick)
        if state:
            self.dirty_states[state.instrument_key] = state

    async def _broadcast_loop(self):
        """Coalesces state updates to avoid excessive Pydantic serializations."""
        while True:
            try:
                await asyncio.sleep(self.broadcast_interval)
                if not self.dirty_states:
                    continue

                for instrument_key, state in list(self.dirty_states.items()):
                    try:
                        dump = state.model_dump()
                        event_bus.publish("order_flow", dump)
                        event_bus.publish("persist_order_flow", dump)
                    except Exception as e:
                        logger.error(f"Error serializing state for {instrument_key}: {e}", exc_info=True)

                # Clear the dirty map after publishing
                self.dirty_states.clear()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}", exc_info=True)

order_flow_processor = OrderFlowTickProcessor()
