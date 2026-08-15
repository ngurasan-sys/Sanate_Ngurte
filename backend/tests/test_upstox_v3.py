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

    # connect() captures the running loop that _on_message dispatches into.
    # There is no streamer here, so this just logs the mock-mode warning.
    await client.connect()

    # Shape emitted by MarketDataStreamerV3 in its default 'ltpc' mode: the
    # protobuf Feed message carries "ltpc" at the top level.
    mock_message = {
        "feeds": {
            "NSE_EQ|INE123": {
                "ltpc": {
                    "ltp": 1500.5,
                    "ltt": "1700000000000",
                    "ltq": "10",
                    "cp": 1495.0,
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
    # Indices have no traded volume and ltpc mode carries no volume field.
    assert tick.volume == 0.0

    await event_bus.stop()


@pytest.mark.asyncio
async def test_on_message_dispatches_from_a_non_asyncio_thread():
    """The SDK invokes on_message from its own websocket thread, where
    asyncio.create_task() would raise. Verify the threadsafe dispatch path."""
    import threading

    client = UpstoxV3Client(api_client=None)

    ticks_received = []

    async def capture_tick(tick):
        ticks_received.append(tick)

    event_bus.subscribe("MARKET_TICK", capture_tick)
    event_bus.start()

    await client.connect()

    message = {"feeds": {"NSE_INDEX|Nifty 50": {"ltpc": {"ltp": 24000.25}}}}

    errors = []

    def worker():
        try:
            client._on_message(message)
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    # Keep the loop free to service call_soon_threadsafe while the thread runs.
    while thread.is_alive():
        await asyncio.sleep(0.01)
    thread.join()

    await asyncio.sleep(0.1)

    assert errors == []
    assert len(ticks_received) == 1
    assert ticks_received[0].price == 24000.25

    await event_bus.stop()


@pytest.mark.asyncio
async def test_on_message_without_a_loop_is_dropped_not_raised():
    client = UpstoxV3Client(api_client=None)
    assert client._loop is None

    # connect() never ran, so there is no loop to dispatch into. This must
    # warn and drop rather than crash the SDK's websocket thread.
    client._on_message({"feeds": {"NSE_INDEX|Nifty 50": {"ltpc": {"ltp": 1.0}}}})


from backend.app.market_data import upstox_v3 as upstox_v3_module


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

    assert client.configure("real-token-123") is True

    assert client.streamer is mock_streamer_instance
    mock_streamer_cls.assert_called_once_with(mock_api_client_cls.return_value, ["NSE_INDEX|Nifty 50"])
    assert mock_streamer_instance.on.call_count == 4


def test_configure_returns_false_without_the_sdk(monkeypatch):
    monkeypatch.setattr(upstox_v3_module, "UPSTOX_AVAILABLE", False)

    client = upstox_v3_module.UpstoxV3Client(instrument_keys=["NSE_INDEX|Nifty 50"])

    assert client.configure("real-token-123") is False
    assert client.streamer is None


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

    # The SDK's streamer exposes disconnect(), not close().
    old_streamer.disconnect.assert_called_once()
    old_streamer.close.assert_not_called()
    assert client.streamer is new_streamer


def test_real_sdk_streamer_uses_disconnect_not_close():
    """Guards the C4 fix against SDK drift: if a future upstox-python-sdk
    renames disconnect() back to close(), this fails loudly instead of the
    shutdown path silently swallowing an AttributeError."""
    if not upstox_v3_module.UPSTOX_AVAILABLE:
        pytest.skip("upstox_client SDK not installed")

    streamer = upstox_v3_module.MarketDataStreamerV3(None, [])
    assert hasattr(streamer, "disconnect")
    assert not hasattr(streamer, "close")


def test_singleton_upstox_client_has_index_subscriptions():
    from backend.app.market_data.symbols import INDEX_INSTRUMENT_KEYS

    assert upstox_v3_module.upstox_client.subscriptions == set(INDEX_INSTRUMENT_KEYS.values())
