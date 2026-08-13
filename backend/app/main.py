from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
from fastapi.middleware.cors import CORSMiddleware

from .api.endpoints import router as api_router, set_level_engine
from .core.db import db_manager
from .core.websocket import websocket_manager
from .core.listeners import DatabaseListeners

from .market_data.processor import TickProcessor
from .market_data.feed import MockFeed
from .levels.engine import LevelEngine
from .strategies.level_based import LevelStrategyEngine
from .engines.opportunity import OpportunityEngine
from .engines.decision import DecisionEngine
from .engines.risk import RiskEngine
from .engines.execution import ExecutionEngine

# Global references to keep them alive
tick_processor = None
mock_feed = None
level_engine = None
strategy_engine = None
opportunity_engine = None
decision_engine = None
risk_engine = None
execution_engine = None
db_listeners = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global tick_processor, mock_feed, level_engine, strategy_engine
    global opportunity_engine, decision_engine, risk_engine, execution_engine, db_listeners

    # Instantiate Engines explicitly
    tick_processor = TickProcessor()
    level_engine = LevelEngine()
    set_level_engine(level_engine)
    strategy_engine = LevelStrategyEngine(level_engine)
    opportunity_engine = OpportunityEngine()
    decision_engine = DecisionEngine()
    risk_engine = RiskEngine()
    execution_engine = ExecutionEngine()

    db_listeners = DatabaseListeners(db_manager, websocket_manager)
    mock_feed = MockFeed(tick_processor)

    # Start explicit EventBus subscriptions
    level_engine.start()
    strategy_engine.start()
    opportunity_engine.start()
    decision_engine.start()
    risk_engine.start()
    execution_engine.start()
    db_listeners.start()

    # Startup background tasks
    task = asyncio.create_task(mock_feed.start())

    yield

    # Shutdown
    mock_feed.stop()
    await task
    db_manager.close()

app = FastAPI(title="Sanate Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
