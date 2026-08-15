import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env BEFORE importing anything that reads env vars at import
# time. The explicit path matters: the app is launched with the repo root as
# CWD, so a bare load_dotenv() would search the wrong directory.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.event_bus import event_bus
from backend.app.api.websockets import router as websocket_router
from backend.app.api.endpoints.order_flow import router as order_flow_router
from backend.app.api.endpoints.levels import router as levels_router
from backend.app.api.endpoints.broker import router as broker_router
from backend.app.api.endpoints.algo import router as algo_router
from backend.app.api.endpoints.live_stream import router as live_stream_router
from backend.app.api.endpoints.execution_control import router as execution_control_router
from backend.app.api.endpoints.brokers import router as brokers_router
from backend.app.api.endpoints.manual_trading import router as manual_trading_router
from backend.app.api.endpoints.algo_config import router as algo_config_router
from backend.app.api.endpoints.cas_dislocation import router as cas_dislocation_router

from backend.app.engines.opportunity import opportunity_engine
from backend.app.engines.decision import decision_engine
from backend.app.engines.risk import risk_engine
from backend.app.engines.execution import execution_engine
from backend.app.order_flow.tick_processor import order_flow_processor
from backend.app.strategies.trending_oi_engine import trending_oi_engine
from backend.app.strategies.trending_oi_price_action.engine import trending_oi_pa_engine
from backend.app.strategies.intraday_trend_scalper.engine import intraday_trend_scalper
from backend.app.strategies.oh_ol import oh_ol_strategy
from backend.app.strategies.straddle.straddle_engine import straddle_engine
from backend.app.strategies.pullback_chop_filter.engine import pullback_chop_filter_engine
from backend.app.strategies.gap_opening.engine import gap_opening_engine
from backend.app.strategies.expiry_reversal import expiry_reversal_engine
from backend.app.strategies.expiry_engine import expiry_oi_tracker_engine
from backend.app.strategies.option_analytics import option_analytics_engine
from backend.app.strategies.manual_trading import manual_trading_engine
from backend.app.strategies.cas_dislocation.engine import cas_dislocation_engine
from backend.app.engines.market_breadth_engine import market_breadth_engine
from backend.app.market_data.upstox_v3 import upstox_client
from backend.app.core import upstox_auth

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

    # STRATEGY_SIGNAL -> OPPORTUNITY_CREATED -> DECISION_CREATED -> risk -> execution.
    # opportunity_engine was previously never started here, so no strategy
    # signal reached risk/execution regardless of DRY_RUN/LIVE mode or the
    # arm switch — this is what actually closes that gap.
    opportunity_engine.start()
    decision_engine.start()
    risk_engine.start()
    execution_engine.start()
    order_flow_processor.start()
    trending_oi_engine.start()
    trending_oi_pa_engine.start()
    intraday_trend_scalper.start()
    oh_ol_strategy.start()
    straddle_engine.start()
    pullback_chop_filter_engine.start()
    gap_opening_engine.start()
    expiry_reversal_engine.start()
    expiry_oi_tracker_engine.start()
    option_analytics_engine.start()
    manual_trading_engine.start()
    cas_dislocation_engine.start()
    market_breadth_engine.start()

    # Start Upstox stream — use a saved token if we have one, otherwise
    # this stays in the existing mock-mode (logs a warning, no crash).
    saved_token = upstox_auth.load_token()
    if saved_token:
        upstox_client.configure(saved_token)
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

        if hasattr(opportunity_engine, "stop"):
            opportunity_engine.stop()

        if hasattr(trending_oi_engine, "stop"):
            trending_oi_engine.stop()

        if hasattr(trending_oi_pa_engine, "stop"):
            trending_oi_pa_engine.stop()
        if hasattr(intraday_trend_scalper, "stop"):
            intraday_trend_scalper.stop()
        if hasattr(oh_ol_strategy, "stop"):
            oh_ol_strategy.stop()
        if hasattr(straddle_engine, "stop"):
            straddle_engine.stop()

        if hasattr(pullback_chop_filter_engine, "stop"):
            pullback_chop_filter_engine.stop()

        if hasattr(gap_opening_engine, "stop"):
            gap_opening_engine.stop()

        if hasattr(expiry_reversal_engine, "stop"):
            expiry_reversal_engine.stop()

        if hasattr(expiry_oi_tracker_engine, "stop"):
            expiry_oi_tracker_engine.stop()

        if hasattr(option_analytics_engine, "stop"):
            option_analytics_engine.stop()

        if hasattr(manual_trading_engine, "stop"):
            manual_trading_engine.stop()

        if hasattr(cas_dislocation_engine, "stop"):
            cas_dislocation_engine.stop()

        if hasattr(market_breadth_engine, "stop"):
            market_breadth_engine.stop()

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

# MUST stay registered before websocket_router: Starlette matches routes
# first-registered-wins, and websocket_router's `/ws/{channel}` wildcard would
# otherwise shadow `/ws/live-stream`. Do not reorder these two.
app.include_router(
    live_stream_router
)

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

app.include_router(
    execution_control_router
)

app.include_router(
    brokers_router
)

app.include_router(
    manual_trading_router
)

app.include_router(
    algo_config_router
)

app.include_router(
    cas_dislocation_router
)




# =============================================================
# HEALTH
# =============================================================

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
    }
