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
        self.active_connections: Dict[str, Dict[WebSocket, asyncio.Queue]] = {
            "market": {},
            "oi": {},
            "quant": {},
            "decisions": {},
            "risk": {},
            "execution": {}
        }
        event_bus.subscribe("market_update", lambda e: self.broadcast("market", e))
        event_bus.subscribe("oi_update", lambda e: self.broadcast("oi", e))
        event_bus.subscribe("decision_created", lambda e: self.broadcast("decisions", e))
        event_bus.subscribe("risk_passed", lambda e: self.broadcast("risk", e))
        event_bus.subscribe("risk_failed", lambda e: self.broadcast("risk", e))
        event_bus.subscribe("execution_update", lambda e: self.broadcast("execution", e))

    async def connect(self, websocket: WebSocket, channel: str):
        if channel in self.active_connections:
            await websocket.accept()
            # Bounded queue per websocket to handle backpressure
            q = asyncio.Queue(maxsize=100)
            self.active_connections[channel][websocket] = q

            # Start a sender task for this websocket
            asyncio.create_task(self._send_loop(websocket, q, channel))
            logger.info(f"Client connected to channel: {channel}")
        else:
            await websocket.close()

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
    await manager.connect(websocket, channel)
    try:
        while True:
            # We receive text to keep the connection alive, allowing for ping/pong logic if needed.
            data = await websocket.receive_text()
            logger.debug(f"Received from client on {channel}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
