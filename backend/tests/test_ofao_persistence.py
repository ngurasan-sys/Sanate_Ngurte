"""Covers the ofao_setups table + insert path added to
workers/persistence.py — no test coverage existed for this worker before
(a pre-existing gap, not introduced here), so this is scoped to the new
addition only.
"""

import asyncio

import pytest

from backend.app.workers.persistence import AsyncPersistenceWorker


@pytest.fixture
def worker():
    return AsyncPersistenceWorker(db_path=":memory:")


def _snapshot(**overrides):
    base = {
        "instrument_key": "NIFTY FUT", "underlying": "NIFTY", "setup_id": "NIFTY_2024-10-01_100000_BULL_001",
        "state": "LOCATION_REACHED", "direction": "BULL", "location_price": 25000.0,
        "absorption_strength": 0.0, "last_price": 25000.0, "timestamp": "2024-10-01T10:00:00Z",
    }
    base.update(overrides)
    return base


def test_ofao_setups_table_created_on_init(worker):
    tables = worker.conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
    table_names = {t[0] for t in tables}
    assert "ofao_setups" in table_names


def test_sync_insert_writes_an_ofao_setup_row(worker):
    worker._sync_insert([("ofao_setup", _snapshot())])
    rows = worker.conn.execute("SELECT instrument_key, setup_id, state, direction FROM ofao_setups").fetchall()
    assert rows == [("NIFTY FUT", "NIFTY_2024-10-01_100000_BULL_001", "LOCATION_REACHED", "BULL")]


def test_sync_insert_handles_multiple_ofao_rows_in_one_batch(worker):
    worker._sync_insert([
        ("ofao_setup", _snapshot(state="LOCATION_REACHED")),
        ("ofao_setup", _snapshot(state="ABSORPTION_DETECTED")),
    ])
    count = worker.conn.execute("SELECT COUNT(*) FROM ofao_setups").fetchone()[0]
    assert count == 2


def test_sync_insert_does_not_affect_other_tables(worker):
    worker._sync_insert([("ofao_setup", _snapshot())])
    assert worker.conn.execute("SELECT COUNT(*) FROM risk_events").fetchone()[0] == 0
    assert worker.conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_enqueue_ofao_event_puts_a_tagged_tuple_on_the_queue(worker):
    await worker._enqueue_ofao_event(_snapshot())
    event_type, event = await worker.queue.get()
    assert event_type == "ofao_setup"
    assert event["instrument_key"] == "NIFTY FUT"
