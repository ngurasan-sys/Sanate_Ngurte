from unittest.mock import AsyncMock

import pytest

from backend.app.engines import execution as execution_module
from backend.app.engines.execution import ExecutionEngine
from backend.app.execution.order_gateway import ExecutionMode, OrderResult


@pytest.mark.asyncio
async def test_execute_order_publishes_persist_execution(monkeypatch):
    published = []

    async def fake_publish(channel, payload):
        published.append((channel, payload))

    monkeypatch.setattr(execution_module.event_bus, "publish", fake_publish)
    monkeypatch.setattr(
        execution_module.order_gateway, "place_order",
        AsyncMock(return_value=OrderResult(status="DRY_RUN", mode=ExecutionMode.DRY_RUN, payload={}, detail="ok")),
    )

    engine = ExecutionEngine()
    await engine.execute_order({
        "instrument": "NIFTY 25000 CE", "instrument_token": "NSE_FO|123",
        "transaction_type": "BUY", "quantity": 75, "price": 100.0,
        "decision_id": "dec_1", "source": "MANUAL",
    })

    persist_events = [p for ch, p in published if ch == "persist_execution"]
    assert len(persist_events) == 1
    assert persist_events[0]["instrument"] == "NIFTY 25000 CE"
    assert persist_events[0]["action"] == "BUY NIFTY 25000 CE"
    assert persist_events[0]["status"] == "DRY_RUN"


@pytest.mark.asyncio
async def test_execute_order_publishes_persist_execution_even_on_rejection(monkeypatch):
    published = []

    async def fake_publish(channel, payload):
        published.append((channel, payload))

    monkeypatch.setattr(execution_module.event_bus, "publish", fake_publish)

    engine = ExecutionEngine()
    await engine.execute_order({
        "instrument": "NIFTY 25000 CE", "instrument_token": None,
        "transaction_type": "BUY", "quantity": 75, "price": 100.0,
        "decision_id": "dec_1", "source": "MANUAL",
    })

    persist_events = [p for ch, p in published if ch == "persist_execution"]
    assert len(persist_events) == 1
    assert persist_events[0]["status"] == "REJECTED"
