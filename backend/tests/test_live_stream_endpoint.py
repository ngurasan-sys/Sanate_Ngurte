import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


def test_live_stream_rejects_unknown_strategy():
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/live-stream?strategy=not_a_real_strategy"):
                pass


def test_live_stream_missing_strategy_param_rejected():
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/live-stream"):
                pass


def test_live_stream_accepts_supported_strategy_and_sends_payload():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live-stream?strategy=trending_oi_price_action") as ws:
            payload = ws.receive_json()

            assert "timestamp" in payload
            assert payload["session_phase"] in {
                "CLOSED", "CONTINUOUS", "DECAY", "CAS", "GOLDEN_WINDOW",
            }
            assert isinstance(payload["risk_status"], list)
            assert isinstance(payload["active_strategy_payload"], dict)
            assert set(payload["market_stats"].keys()) == {
                "regime", "oi_difference_pct", "atr_progress_pct",
            }


def test_live_stream_strategy_without_adapter_reports_empty_risk_status():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live-stream?strategy=straddle") as ws:
            payload = ws.receive_json()
            assert payload["risk_status"] == []
