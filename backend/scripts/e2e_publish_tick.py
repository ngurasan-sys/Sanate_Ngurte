import sys


from datetime import datetime, timezone
import asyncio
import threading
import sys

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.event_bus import event_bus
from backend.app.market_data.models import Tick
def run():
    # We'll run the ASGI application lifespan by entering TestClient context
    # but instead of using a real TestClient websocket (which can be
    # fragile in this harness), register a DummyWebSocket directly with the
    # production ConnectionManager. This still exercises the event-bus ->
    # manager -> per-connection queue -> send loop flow without changing
    # production code.
    class DummyWS:
        def __init__(self):
            self.received = []
            self.evt = threading.Event()

        async def send_json(self, msg):
            self.received.append(msg)
            self.evt.set()

    tick_obj = Tick(
        instrument="E2E_TEST",
        price=42.5,
        volume=1.0,
        timestamp=datetime.now(timezone.utc),
    )

    with TestClient(app) as client:
        # app startup has run; locate manager and register a DummyWS
        from backend.app.api.websockets import manager

        dummy = DummyWS()
        # create a bounded queue similar to manager.connect
        q = asyncio.Queue()
        manager.active_connections.setdefault("chart", {})
        manager.active_connections["chart"][dummy] = q

        # start the send loop for our dummy websocket on the server loop
        # by scheduling the manager._send_loop coroutine on the server's
        # event loop (same pattern as subscriptions use).
        import backend.app.core.event_bus as eb_mod
        eb = eb_mod.event_bus
        if not eb._workers:
            raise RuntimeError("Event bus workers not started; cannot schedule send loop")

        server_loop = eb._workers[0].get_loop()

        send_task = asyncio.run_coroutine_threadsafe(
            manager._send_loop(dummy, q, "chart"),
            server_loop,
        )

        try:
            # Schedule publish on the server loop
            pub_fut = asyncio.run_coroutine_threadsafe(
                eb.publish("MARKET_TICK", tick_obj),
                server_loop,
            )
            pub_fut.result(timeout=1.0)

            # Wait up to 2s for the dummy ws to receive the message
            if not dummy.evt.wait(timeout=2.0):
                print("No message received by DummyWS within timeout")
                raise SystemExit(3)

            payload = dummy.received[0]
            print("DummyWS received:", payload)

            # Validate
            if not isinstance(payload, dict):
                print("Invalid payload type")
                raise SystemExit(5)

            assert payload.get('instrument') == tick_obj.instrument
            assert float(payload.get('price')) == float(tick_obj.price)

        finally:
            # Cancel the send loop task
            try:
                send_task.cancel()
                send_task.result(timeout=1.0)
            except Exception:
                pass


if __name__ == '__main__':
    run()
