import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.event_bus import event_bus
from backend.app.api.websockets import router as websocket_router
from backend.app.api.endpoints.order_flow import router as order_flow_router
from backend.app.api.endpoints.levels import router as levels_router
from backend.app.api.endpoints.broker import router as broker_router
from backend.app.api.endpoints.algo import router as algo_router

from backend.app.engines.decision import decision_engine
from backend.app.engines.risk import risk_engine
from backend.app.engines.execution import execution_engine
from backend.app.order_flow.tick_processor import order_flow_processor
from backend.app.strategies.trending_oi_engine import trending_oi_engine
from backend.app.strategies.oh_ol import oh_ol_strategy
from backend.app.market_data.upstox_v3 import UpstoxV3Client

# Mock or global instance
upstox_client = UpstoxV3Client()

# =============================================================
# LOGGING
# =============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s - %(name)s - "
        "%(levelname)s - %(message)s"
    ),
)

logger = logging.getLogger(__name__)


# =============================================================
# APPLICATION LIFECYCLE
# =============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle.

    Starts the shared EventBus, downstream engines, order flow processor,
    and persistence worker when the application starts.

    Stops them cleanly during application shutdown.
    """

    logger.info(
        "Starting Algo Trading Workstation..."
    )

    # ---------------------------------------------------------
    # Event Bus
    # ---------------------------------------------------------

    event_bus.start()

    # ---------------------------------------------------------
    # Downstream Engines & Processors
    # ---------------------------------------------------------

    decision_engine.start()
    risk_engine.start()
    execution_engine.start()
    order_flow_processor.start()
    trending_oi_engine.start()
    oh_ol_strategy.start()

    # Start Upstox stream
    asyncio.create_task(upstox_client.connect())

    # ---------------------------------------------------------
    # Persistence Worker (lazy import)
    # ---------------------------------------------------------
    try:
        from backend.app.workers.persistence import persistence_worker
        persistence_task = asyncio.create_task(persistence_worker.run())
    except Exception:
        persistence_task = None

    logger.info(
        "Application startup completed. "
        "Event bus, engines, order flow processor and persistence worker "
        "are running."
    )

    try:
        yield

    finally:
        logger.info(
            "Application shutting down..."
        )

        # -----------------------------------------------------
        # Stop persistence worker
        # -----------------------------------------------------
        if persistence_task:
            persistence_task.cancel()
            try:
                await persistence_task
            except asyncio.CancelledError:
                pass

        # -----------------------------------------------------
        # Stop downstream engines & processors
        # -----------------------------------------------------

        if hasattr(order_flow_processor, "stop"):
            order_flow_processor.stop()

        if hasattr(execution_engine, "stop"):
            execution_engine.stop()

        if hasattr(risk_engine, "stop"):
            risk_engine.stop()

        if hasattr(decision_engine, "stop"):
            decision_engine.stop()

        if hasattr(trending_oi_engine, "stop"):
            trending_oi_engine.stop()

        if hasattr(oh_ol_strategy, "stop"):
            oh_ol_strategy.stop()

        if hasattr(upstox_client, "close"):
            await upstox_client.close()

        # -----------------------------------------------------
        # Stop Event Bus
        # -----------------------------------------------------

        if hasattr(event_bus, "stop"):
            result = event_bus.stop()

            if asyncio.iscoroutine(result):
                await result

        logger.info(
            "Application shutdown completed."
        )


# =============================================================
# FASTAPI APPLICATION
# =============================================================

app = FastAPI(
    title="Algo Trading Workstation",
    version="1.0.0",
    description=(
        "Professional algorithmic trading "
        "backend infrastructure."
    ),
    lifespan=lifespan,
)


# =============================================================
# CORS
# =============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================
# ROUTERS
# =============================================================

app.include_router(
    websocket_router
)

app.include_router(
    order_flow_router
)

app.include_router(
    levels_router
)

app.include_router(
    broker_router
)

app.include_router(
    algo_router
)




# =============================================================
# HEALTH
# =============================================================

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
    }
