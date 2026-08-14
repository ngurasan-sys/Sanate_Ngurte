import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
from backend.app.core.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        # Using bounded queues per connection for backpressure handling
        # Add 'chart' and 'levels' channels explicitly so /ws/levels and the
        # chart stream endpoint are supported by this manager.
        self.active_connections: Dict[str, Dict[WebSocket, asyncio.Queue]] = {
            "market": {},
            "chart": {},
            "oi": {},
            "quant": {},
            "decisions": {},
            "risk": {},
            "execution": {},
            "order_flow": {},
            "levels": {},
            "algo": {},
            "trending_oi": {}
        }

        # Subscribe to events from the event bus and forward to websocket
        # channels. Convert pydantic models to dicts when needed.
        event_bus.subscribe("MARKET_TICK", lambda e: self._publish_model_or_dict("chart", e))
        event_bus.subscribe("LEVEL_CREATED", lambda e: self._publish_model_or_dict("levels", e))
        event_bus.subscribe("order_flow", lambda e: self.broadcast("order_flow", e))
        event_bus.subscribe("execution_update", lambda e: self.broadcast("execution", e))
        event_bus.subscribe("decision_created", lambda e: self.broadcast("decisions", e))
        event_bus.subscribe("risk_passed", lambda e: self.broadcast("risk", e))
        event_bus.subscribe("risk_failed", lambda e: self.broadcast("risk", e))
        # Algo dashboard events
        event_bus.subscribe("ALGO_STATUS", lambda e: self.broadcast("algo", e))
        event_bus.subscribe("STRATEGY_STATUS", lambda e: self.broadcast("algo", e))
        event_bus.subscribe("SIGNAL_CREATED", lambda e: self.broadcast("algo", e))
        event_bus.subscribe("DECISION_CREATED", lambda e: self.broadcast("algo", e))
        event_bus.subscribe("RISK_DECISION", lambda e: self.broadcast("algo", e))
        event_bus.subscribe("EXECUTION_UPDATE", lambda e: self.broadcast("algo", e))
        event_bus.subscribe("trending_oi", lambda e: self.broadcast("trending_oi", e))

    def _publish_model_or_dict(self, channel: str, payload):
        try:
            if hasattr(payload, "model_dump"):
                msg = payload.model_dump()
            else:
                msg = payload
        except Exception:
            msg = payload

        # Fire-and-forget, keep non-blocking
        try:
            asyncio.create_task(self.broadcast(channel, msg))
        except Exception:
            logger.exception("Failed to schedule broadcast task")

    async def connect(self, websocket: WebSocket, channel: str) -> bool:
        """Attempt to connect a websocket to a named channel.

        Returns True when the connection was accepted and registered.
        Returns False when the channel is unknown and the socket was closed.
        """
        if channel in self.active_connections:
            await websocket.accept()
            # Bounded queue per websocket to handle backpressure
            q = asyncio.Queue(maxsize=100)
            self.active_connections[channel][websocket] = q

            # Start a sender task for this websocket
            asyncio.create_task(self._send_loop(websocket, q, channel))
            logger.info(f"Client connected to channel: {channel}")
            return True
        else:
            # Reject unknown channels cleanly without attempting receives.
            try:
                await websocket.close(code=1003)
            except Exception:
                pass
            return False

    def disconnect(self, websocket: WebSocket, channel: str):
        if channel in self.active_connections and websocket in self.active_connections[channel]:
            del self.active_connections[channel][websocket]
            logger.info(f"Client disconnected from channel: {channel}")

    async def _send_loop(self, websocket: WebSocket, queue: asyncio.Queue, channel: str):
        """Dedicated sender loop for each websocket to pull from its bounded queue."""
        try:
            while True:
                message = await queue.get()
                await websocket.send_json(message)
                queue.task_done()
        except Exception:
            self.disconnect(websocket, channel)

    async def broadcast(self, channel: str, message: dict):
        if channel not in self.active_connections:
            return

        dead_connections = []
        for ws, q in self.active_connections[channel].items():
            try:
                # Use put_nowait to avoid blocking the event bus on a slow client
                q.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning(f"WebSocket queue full for channel {channel}, dropping message for slow client.")
            except Exception:
                dead_connections.append(ws)

        for dead in dead_connections:
            self.disconnect(dead, channel)

manager = ConnectionManager()

@router.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    accepted = await manager.connect(websocket, channel)
    if not accepted:
        # Connection was rejected; do not attempt receives.
        return

    try:
        while True:
            # We receive text to keep the connection alive, allowing for ping/pong logic if needed.
            data = await websocket.receive_text()
            logger.debug(f"Received from client on {channel}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


@router.websocket("/api/v1/chart/stream")
async def chart_stream(websocket: WebSocket):
    # Use the 'chart' channel for market tick streaming
    accepted = await manager.connect(websocket, "chart")
    if not accepted:
        return

    try:
        while True:
            data = await websocket.receive_text()
            # Basic ping/pong support
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, "chart")
