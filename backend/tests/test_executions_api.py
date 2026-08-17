from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.workers.persistence import persistence_worker


@pytest.fixture
def client():
    return TestClient(app)


def _insert_execution(instrument: str, action: str, status: str):
    persistence_worker.conn.execute(
        "INSERT INTO executions (instrument, action, status) VALUES (?, ?, ?)",
        [instrument, action, status],
    )


def test_get_executions_returns_most_recent_first(client):
    _insert_execution("NIFTY 25000 CE", "BUY NIFTY 25000 CE", "DRY_RUN")
    _insert_execution("SENSEX 80000 PE", "SELL SENSEX 80000 PE", "SUBMITTED")

    res = client.get("/api/v1/executions")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) >= 2
    # most recent insert (SENSEX) appears before the earlier one (NIFTY)
    sensex_idx = next(i for i, r in enumerate(rows) if r["instrument"] == "SENSEX 80000 PE")
    nifty_idx = next(i for i, r in enumerate(rows) if r["instrument"] == "NIFTY 25000 CE")
    assert sensex_idx < nifty_idx
    assert rows[sensex_idx]["status"] == "SUBMITTED"


def test_get_executions_respects_limit(client):
    for i in range(5):
        _insert_execution(f"TEST{i}", f"BUY TEST{i}", "DRY_RUN")

    res = client.get("/api/v1/executions?limit=3")
    assert res.status_code == 200
    assert len(res.json()) == 3
