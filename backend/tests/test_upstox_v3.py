import pytest
import asyncio
from unittest.mock import MagicMock
from backend.app.market_data.upstox_v3 import UpstoxV3Client
from backend.app.core.event_bus import event_bus

@pytest.mark.asyncio
async def test_upstox_v3_message_processing():
    client = UpstoxV3Client(api_client=None)

    ticks_received = []

    async def capture_tick(tick):
        ticks_received.append(tick)

    event_bus.subscribe("MARKET_TICK", capture_tick)

    # We must start the event bus to process messages
    event_bus.start()

    mock_message = {
        "feeds": {
            "NSE_EQ|INE123": {
                "ff": {
                    "marketFF": {
                        "ltpc": {
                            "ltp": 1500.5
                        },
                        "v": 50000
                    }
                }
            }
        }
    }

    # Simulate receiving a decoded protobuf message
    client._on_message(mock_message)

    # Wait for the async task and event bus to process
    await asyncio.sleep(0.1)

    assert len(ticks_received) == 1
    tick = ticks_received[0]
    assert tick.instrument == "NSE_EQ|INE123"
    assert tick.price == 1500.5
    assert tick.volume == 50000

    await event_bus.stop()
