import asyncio
import pytest

from backend.app.api.websockets import ConnectionManager


class DummyWebSocket:
    def __init__(self):
        self.received = []
        self._evt = asyncio.Event()

    async def send_json(self, message):
        self.received.append(message)
        self._evt.set()


@pytest.mark.asyncio
async def test_manager_broadcasts_market_tick_to_clients():
    manager = ConnectionManager()

    # Prepare a dummy websocket and a dedicated queue for the 'chart' channel
    ws = DummyWebSocket()
    q = asyncio.Queue()

    # Register the dummy websocket into the manager
    manager.active_connections.setdefault("chart", {})
    manager.active_connections["chart"][ws] = q

    # Start the send loop that will read from the queue and call send_json
    send_task = asyncio.create_task(manager._send_loop(ws, q, "chart"))

    try:
        # Broadcast a MARKET_TICK-like payload
        payload = {"instrument": "TEST", "ltp": 123.45, "timestamp": 1234567890}
        await manager.broadcast("chart", payload)

        # Wait for the dummy websocket to receive the message
        await asyncio.wait_for(ws._evt.wait(), timeout=1.0)

        assert len(ws.received) == 1
        assert ws.received[0] == payload
    finally:
        send_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await send_task
