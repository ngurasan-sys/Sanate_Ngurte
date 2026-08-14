import pytest
import asyncio
from datetime import datetime, timezone
from backend.app.market_data.models import Tick
from backend.app.market_data.processor import TickProcessor
from backend.app.levels.engine import LevelEngine
from backend.app.strategies.level_based import LevelStrategyEngine
from backend.app.engines.opportunity import OpportunityEngine
from backend.app.engines.decision import DecisionEngine
from backend.app.engines.risk import RiskEngine
from backend.app.engines.execution import ExecutionEngine
from backend.app.core.event_bus import event_bus

@pytest.mark.asyncio
async def test_full_event_flow():
    # Clear event bus to prevent bleed from other tests
    event_bus._pending_subscriptions.clear()
    event_bus._subscriber_queues.clear()
    event_bus._workers.clear()
    event_bus._started = False

    tick_processor = TickProcessor()
    level_engine = LevelEngine()
    strategy_engine = LevelStrategyEngine(level_engine)
    opportunity_engine = OpportunityEngine()
    decision_engine = DecisionEngine()
    risk_engine = RiskEngine()
    execution_engine = ExecutionEngine()

    level_engine.start()
    strategy_engine.start()
    opportunity_engine.start()
    decision_engine.start()
    risk_engine.start()
    execution_engine.start()
    event_bus.start()

    captured_events = []

    async def capture(data, ev_type):
        captured_events.append(ev_type)

    event_bus.subscribe("CANDLE_CLOSED", lambda d: asyncio.create_task(capture(d, "CANDLE_CLOSED")))
    event_bus.subscribe("LEVEL_CREATED", lambda d: asyncio.create_task(capture(d, "LEVEL_CREATED")))
    event_bus.subscribe("STRATEGY_SIGNAL", lambda d: asyncio.create_task(capture(d, "STRATEGY_SIGNAL")))
    event_bus.subscribe("OPPORTUNITY_CREATED", lambda d: asyncio.create_task(capture(d, "OPPORTUNITY_CREATED")))
    event_bus.subscribe("DECISION_CREATED", lambda d: asyncio.create_task(capture(d, "DECISION_CREATED")))
    event_bus.subscribe("RISK_DECISION", lambda d: asyncio.create_task(capture(d, "RISK_DECISION")))
    event_bus.subscribe("EXECUTION_REQUEST", lambda d: asyncio.create_task(capture(d, "EXECUTION_REQUEST")))

    # Candle 1
    t1 = Tick(instrument="NIFTY", price=100, volume=10, timestamp=datetime(2023,1,1,9,15,0, tzinfo=timezone.utc))
    await tick_processor.process(t1)

    # Candle 2 (closes C1)
    t2 = Tick(instrument="NIFTY", price=120, volume=10, timestamp=datetime(2023,1,1,9,20,0, tzinfo=timezone.utc))
    await tick_processor.process(t2)

    # Candle 3 (closes C2)
    t3 = Tick(instrument="NIFTY", price=110, volume=10, timestamp=datetime(2023,1,1,9,25,0, tzinfo=timezone.utc))
    await tick_processor.process(t3)

    # Candle 4 (closes C3)
    t4 = Tick(instrument="NIFTY", price=105, volume=10, timestamp=datetime(2023,1,1,9,30,0, tzinfo=timezone.utc))
    await tick_processor.process(t4)

    await asyncio.sleep(0.1)

    assert "CANDLE_CLOSED" in captured_events
    assert "LEVEL_CREATED" in captured_events

    t5 = Tick(instrument="NIFTY", price=119.9, volume=10, timestamp=datetime(2023,1,1,9,32,0, tzinfo=timezone.utc))
    await tick_processor.process(t5)

    await asyncio.sleep(0.1)

    assert "STRATEGY_SIGNAL" in captured_events
    assert "OPPORTUNITY_CREATED" in captured_events
    assert "DECISION_CREATED" in captured_events
    assert "RISK_DECISION" in captured_events
    assert "EXECUTION_REQUEST" in captured_events
