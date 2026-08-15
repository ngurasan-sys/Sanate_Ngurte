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


import backend.app.market_data.upstox_v3 as upstox_v3_module


def test_configure_builds_live_streamer(monkeypatch):
    mock_streamer_instance = MagicMock()
    mock_streamer_cls = MagicMock(return_value=mock_streamer_instance)
    mock_api_client_cls = MagicMock()
    mock_configuration_cls = MagicMock()

    monkeypatch.setattr(upstox_v3_module, "UPSTOX_AVAILABLE", True)
    monkeypatch.setattr(upstox_v3_module, "MarketDataStreamerV3", mock_streamer_cls)
    monkeypatch.setattr(upstox_v3_module, "ApiClient", mock_api_client_cls)
    monkeypatch.setattr(upstox_v3_module, "Configuration", mock_configuration_cls)

    client = upstox_v3_module.UpstoxV3Client(instrument_keys=["NSE_INDEX|Nifty 50"])
    assert client.streamer is None  # still mock mode before configure()

    client.configure("real-token-123")

    assert client.streamer is mock_streamer_instance
    mock_streamer_cls.assert_called_once_with(mock_api_client_cls.return_value, ["NSE_INDEX|Nifty 50"])
    assert mock_streamer_instance.on.call_count == 4


def test_configure_closes_existing_streamer_first(monkeypatch):
    old_streamer = MagicMock()
    new_streamer = MagicMock()
    mock_streamer_cls = MagicMock(return_value=new_streamer)

    monkeypatch.setattr(upstox_v3_module, "UPSTOX_AVAILABLE", True)
    monkeypatch.setattr(upstox_v3_module, "MarketDataStreamerV3", mock_streamer_cls)
    monkeypatch.setattr(upstox_v3_module, "ApiClient", MagicMock())
    monkeypatch.setattr(upstox_v3_module, "Configuration", MagicMock())

    client = upstox_v3_module.UpstoxV3Client(instrument_keys=["NSE_INDEX|Nifty 50"])
    client.streamer = old_streamer

    client.configure("real-token-123")

    old_streamer.close.assert_called_once()
    assert client.streamer is new_streamer


def test_singleton_upstox_client_has_index_subscriptions():
    from backend.app.market_data.symbols import INDEX_INSTRUMENT_KEYS

    assert upstox_v3_module.upstox_client.subscriptions == set(INDEX_INSTRUMENT_KEYS.values())
