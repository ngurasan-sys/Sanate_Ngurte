import pytest
from backend.app.engines.greeks_engine import GreeksEngine
from backend.app.core.event_bus import event_bus

@pytest.mark.asyncio
async def test_greeks_engine_publish():
    engine = GreeksEngine()

    events = []
    async def on_greeks_updated(data):
        events.append(data)

    event_bus._pending_subscriptions.clear()
    event_bus._subscriber_queues.clear()
    event_bus._workers.clear()
    event_bus._started = False

    event_bus.subscribe("GREEKS_UPDATED", on_greeks_updated)
    event_bus.start()

    input_data = {
        "instrument": "TEST_CE",
        "underlying": "TEST",
        "expiry": "2024-01-01",
        "strike": 100.0,
        "option_type": "CALL",
        "spot_price": 100.0,
        "option_price": 10.450583,
        "time_to_expiry": 1.0,
        "timestamp": 123456789.0
    }

    await engine.calculate_and_publish(input_data)

    import asyncio
    await asyncio.sleep(0.1) # allow event bus to process

    assert len(events) == 1
    assert events[0].instrument == "TEST_CE"
    assert events[0].implied_volatility is not None
