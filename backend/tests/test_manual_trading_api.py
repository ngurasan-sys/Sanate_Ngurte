from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.endpoints.manual_trading import router as manual_trading_router
from backend.app.strategies.manual_trading.engine import manual_trading_engine

app = FastAPI()
app.include_router(manual_trading_router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_positions():
    manual_trading_engine.positions.clear()
    yield
    manual_trading_engine.positions.clear()


def test_get_lot_sizes():
    response = client.get("/api/v1/manual-trading/lot-sizes")
    assert response.status_code == 200
    body = response.json()
    assert body["NIFTY"] == 65
    assert body["BANKNIFTY"] == 30
    assert body["SENSEX"] == 20


def test_list_positions_empty_initially():
    response = client.get("/api/v1/manual-trading/positions")
    assert response.status_code == 200
    assert response.json() == []


def _row(strike, call_ltp=100.0):
    # instrument_key is a sibling of market_data in the real Upstox
    # response (verified live), not nested inside it.
    return {
        "strike_price": strike,
        "underlying_spot_price": 24500.0,
        "call_options": {"instrument_key": "CE1", "market_data": {"ltp": call_ltp}},
        "put_options": {"instrument_key": "PE1", "market_data": {"ltp": 90.0}},
    }


CHAIN = [_row(24500)]


def test_place_order_endpoint_success():
    with patch("backend.app.strategies.manual_trading.engine.upstox_auth.load_token", return_value="tok"), \
         patch("backend.app.strategies.manual_trading.engine.fetch_option_chain", new=AsyncMock(return_value=CHAIN)), \
         patch("backend.app.strategies.manual_trading.engine.event_bus.publish", new=AsyncMock()):
        response = client.post("/api/v1/manual-trading/order", json={
            "underlying": "NIFTY", "option_type": "CE", "strike": 24500.0,
            "lots": 1, "stop_loss": 50.0, "target": 150.0, "pyramid_lot_size": 1,
        })

    assert response.status_code == 200
    body = response.json()
    assert body["quantity"] == 65
    # PENDING, not OPEN: the response comes back before RISK_DECISION/
    # EXECUTION_UPDATE confirm anything — event_bus.publish is mocked to a
    # no-op here, so no confirmation ever arrives in this test.
    assert body["status"] == "PENDING"


def test_place_order_endpoint_rejects_bad_stop_loss():
    with patch("backend.app.strategies.manual_trading.engine.upstox_auth.load_token", return_value="tok"), \
         patch("backend.app.strategies.manual_trading.engine.fetch_option_chain", new=AsyncMock(return_value=CHAIN)), \
         patch("backend.app.strategies.manual_trading.engine.event_bus.publish", new=AsyncMock()):
        response = client.post("/api/v1/manual-trading/order", json={
            "underlying": "NIFTY", "option_type": "CE", "strike": 24500.0,
            "lots": 1, "stop_loss": 200.0, "target": 150.0, "pyramid_lot_size": 0,
        })

    assert response.status_code == 400
    assert "stop_loss" in response.json()["detail"]


def test_pyramid_endpoint_unknown_position_returns_400():
    response = client.post("/api/v1/manual-trading/pyramid/MANUAL_missing")
    assert response.status_code == 400


def test_close_endpoint_unknown_position_returns_400():
    response = client.post("/api/v1/manual-trading/close/MANUAL_missing")
    assert response.status_code == 400
