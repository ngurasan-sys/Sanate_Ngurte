from fastapi.testclient import TestClient
import pytest

from backend.app.main import app


def test_ws_levels_accepts():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/levels") as ws:
            # If we connected, the context manager returned without error
            assert ws is not None


def test_invalid_channel_rejected():
    with TestClient(app) as client:
        with pytest.raises(Exception):
            # Attempting to connect to an unknown channel should fail
            with client.websocket_connect("/ws/unknown_channel"):
                pass


def test_chart_stream_accepts():
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/chart/stream") as ws:
            assert ws is not None


def test_multiple_chart_clients():
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/chart/stream") as ws1:
            with client.websocket_connect("/api/v1/chart/stream") as ws2:
                assert ws1 is not None and ws2 is not None
