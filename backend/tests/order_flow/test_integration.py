import pytest
import asyncio
from backend.app.core.event_bus import event_bus
from backend.app.api.websockets import manager
from backend.app.order_flow.tick_processor import order_flow_processor

@pytest.mark.asyncio
async def test_order_flow_ws_isolation():
    manager.active_connections["order_flow"] = {}
    manager.active_connections["market"] = {}

    # Send a mock tick to event bus
    tick = {
        "instrument_key": "NIFTY_WS_TEST",
        "ltp": 100.0,
        "ltq": 50,
        "volume": 50
    }

    await order_flow_processor.on_market_tick(tick)

    # Verify that order_flow state was calculated
    state = order_flow_processor.engine.get_state("NIFTY_WS_TEST")
    assert state is not None
    assert state.instrument_key == "NIFTY_WS_TEST"

@pytest.mark.asyncio
async def test_rest_api_endpoint():
    from fastapi.testclient import TestClient
    from backend.app.main import app

    # Pre-populate state properly so trade size evaluates appropriately
    # Trade size evaluates as valid when volume changes
    tick1 = {
        "instrument_key": "NIFTY_REST",
        "ltp": 100.0,
        "ltq": 0,
        "volume": 0
    }
    await order_flow_processor.on_market_tick(tick1)

    tick2 = {
        "instrument_key": "NIFTY_REST",
        "ltp": 100.0,
        "ltq": 50,
        "volume": 50
    }
    await order_flow_processor.on_market_tick(tick2)

    with TestClient(app) as client:
        response = client.get("/api/v1/order-flow/NIFTY_REST")
        assert response.status_code == 200
        data = response.json()
        assert data["instrument_key"] == "NIFTY_REST"
        assert data["trade_size"] == 50

        # Test not found
        response = client.get("/api/v1/order-flow/UNKNOWN")
        assert response.status_code == 404
