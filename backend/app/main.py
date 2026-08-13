import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.event_bus import event_bus
from backend.app.api.websockets import router as websocket_router
from backend.app.workers.persistence import persistence_worker

# Import engine modules only if their definitions are required
# elsewhere. Do not rely on imports for hidden initialization.
from backend.app.engines.decision import decision_engine
from backend.app.engines.risk import risk_engine
from backend.app.engines.execution import execution_engine


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s - %(name)s - "
        "%(levelname)s - %(message)s"
    ),
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle.

    All long-running infrastructure and downstream engines
    are explicitly started and stopped here.
    """

    logger.info("Starting Algo Trading Workstation...")

    # ---------------------------------------------------------
    # Event Bus
    # ---------------------------------------------------------

    event_bus.start()

    # ---------------------------------------------------------
    # Downstream Engines
    # ---------------------------------------------------------

    decision_engine.start()
    risk_engine.start()
    execution_engine.start()

    # ---------------------------------------------------------
    # Persistence Worker
    # ---------------------------------------------------------

    persistence_task = asyncio.create_task(
        persistence_worker.run()
    )

    logger.info(
        "Application startup completed. "
        "Event bus, engines and persistence worker are running."
    )

    try:
        yield

    finally:
        logger.info("Application shutting down...")

        # -----------------------------------------------------
        # Stop persistence worker
        # -----------------------------------------------------

        persistence_task.cancel()

        try:
            await persistence_task
        except asyncio.CancelledError:
            pass

        # -----------------------------------------------------
        # Stop downstream engines
        # -----------------------------------------------------

        execution_engine.stop()
        risk_engine.stop()
        decision_engine.stop()

        # -----------------------------------------------------
        # Stop Event Bus
        # -----------------------------------------------------

        event_bus.stop()

        logger.info(
            "Application shutdown completed."
        )


app = FastAPI(
    title="Algo Trading Workstation",
    version="1.0.0",
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
# WEBSOCKET
# =============================================================

app.include_router(websocket_router)


# =============================================================
# HEALTH
# =============================================================

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
    }