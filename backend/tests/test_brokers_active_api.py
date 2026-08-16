import pytest
from fastapi.testclient import TestClient

from backend.app.core import active_broker as ab_module
from backend.app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ab_module, "STATE_PATH", tmp_path / "active_broker.json")
    monkeypatch.setattr(ab_module.active_broker, "_active_broker_id", None)
    return TestClient(app)


def test_get_active_broker_starts_as_null(client):
    res = client.get("/api/v1/brokers/active")
    assert res.status_code == 200
    assert res.json() == {"broker_id": None}


def test_post_active_broker_rejects_unknown_broker(client):
    res = client.post("/api/v1/brokers/active", json={"broker_id": "not_real"})
    assert res.status_code == 400


def test_post_active_broker_rejects_unready_broker(client):
    res = client.post("/api/v1/brokers/active", json={"broker_id": "dhan"})
    assert res.status_code == 400
    assert "not connected" in res.json()["detail"] or "registered" in res.json()["detail"]
