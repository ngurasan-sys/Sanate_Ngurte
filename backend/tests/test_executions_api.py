from datetime import datetime, timedelta

import duckdb
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.workers.persistence import AsyncPersistenceWorker


@pytest.fixture
def isolated_worker(monkeypatch):
    """An in-memory DuckDB persistence worker, patched over the module-level
    singleton the executions endpoint reads. Keeps test rows out of the real
    analytics.duckdb file (which the endpoint's singleton opens relative to
    CWD) and makes ordering assertions depend only on this test's own rows.
    """
    # Build the worker without running __init__: the real __init__ subscribes
    # to the (possibly already-running) global event bus, which needs a live
    # event loop. The endpoint only ever touches `.conn`.
    worker = object.__new__(AsyncPersistenceWorker)
    worker.db_path = ":memory:"
    worker.conn = duckdb.connect(":memory:")
    worker._init_db()
    monkeypatch.setattr(
        "backend.app.api.endpoints.executions.persistence_worker", worker
    )
    yield worker
    worker.conn.close()


@pytest.fixture
def client(isolated_worker):
    return TestClient(app)


def _insert_execution(worker, instrument: str, action: str, status: str, ts: datetime):
    worker.conn.execute(
        "INSERT INTO executions (timestamp, instrument, action, status) VALUES (?, ?, ?, ?)",
        [ts, instrument, action, status],
    )


def test_get_executions_returns_most_recent_first(client, isolated_worker):
    base = datetime(2024, 1, 1, 9, 15, 0)
    _insert_execution(isolated_worker, "NIFTY 25000 CE", "BUY NIFTY 25000 CE", "DRY_RUN", base)
    _insert_execution(
        isolated_worker, "SENSEX 80000 PE", "SELL SENSEX 80000 PE", "SUBMITTED", base + timedelta(minutes=1)
    )

    res = client.get("/api/v1/executions")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 2
    # most recent insert (SENSEX) appears before the earlier one (NIFTY)
    assert rows[0]["instrument"] == "SENSEX 80000 PE"
    assert rows[0]["status"] == "SUBMITTED"
    assert rows[1]["instrument"] == "NIFTY 25000 CE"


def test_get_executions_respects_limit(client, isolated_worker):
    base = datetime(2024, 1, 1, 9, 15, 0)
    for i in range(5):
        _insert_execution(isolated_worker, f"TEST{i}", f"BUY TEST{i}", "DRY_RUN", base + timedelta(minutes=i))

    res = client.get("/api/v1/executions?limit=3")
    assert res.status_code == 200
    assert len(res.json()) == 3


def test_get_executions_rejects_out_of_range_limit(client):
    assert client.get("/api/v1/executions?limit=0").status_code == 422
