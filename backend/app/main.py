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
from backend.app.api.endpoints.backtest import router as backtest_router
from backend.app.api.endpoints.footprint import router as footprint_router
from backend.app.api.endpoints.ofao import router as ofao_router
from backend.app.api.endpoints.executions import router as executions_router
from backend.app.api.endpoints.market import router as market_router, set_gap_opening_engine as market_set_gap_opening
from backend.app.api.endpoints.strategies import router as strategies_router
from backend.app.api.endpoints.risk_summary import router as risk_summary_router, set_risk_engine as risk_set_risk_engine
from backend.app.api.endpoints.decisions_api import router as decisions_router, set_decision_engine as decisions_set_decision
from backend.app.api.endpoints.option_chain import router as option_chain_router, set_option_analytics_engine as option_set_analytics

from backend.app.engines.opportunity import opportunity_engine
from backend.app.engines.decision import decision_engine
from backend.app.engines.risk import risk_engine
from backend.app.engines.execution import execution_engine
from backend.app.order_flow.tick_processor import order_flow_processor
from backend.app.order_flow.footprint_processor import footprint_processor
from backend.app.order_flow.mock_feed import mock_footprint_feed
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
from backend.app.strategies.order_flow_absorption.engine import ofao_engine
from backend.app.engines.market_breadth_engine import market_breadth_engine
from backend.app.market_data.processor import TickProcessor
from backend.app.levels.engine import LevelEngine
from backend.app.api.endpoints.levels import set_level_engine
from backend.app.market_data.upstox_provider import upstox_provider
from backend.app.execution.upstox_adapter import upstox_execution_adapter
from backend.app.core import upstox_auth
from backend.app.market_data.dhan_provider import dhan_provider
from backend.app.execution.dhan_adapter import dhan_execution_adapter
from backend.app.core import dhan_auth
from backend.app.core.active_broker import active_broker

# Registering here (module import time) means active_broker knows about
# Upstox as soon as the app process exists — readiness (is_broker_ready)
# still gates whether it can actually be activated.
active_broker.register_broker(
    "upstox", provider=upstox_provider, execution_adapter=upstox_execution_adapter, auth_module=upstox_auth,
)

active_broker.register_broker(
    "dhan", provider=dhan_provider, execution_adapter=dhan_execution_adapter, auth_module=dhan_auth,
)

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
    footprint_processor.start()
    mock_footprint_feed.start()
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
    ofao_engine.start()
    market_breadth_engine.start()

    tick_processor = TickProcessor()
    level_engine = LevelEngine()
    set_level_engine(level_engine)
    level_engine.start()

    # Inject engine instances for API endpoints
    market_set_gap_opening(gap_opening_engine)
    risk_set_risk_engine(risk_engine)
    decisions_set_decision(decision_engine)
    option_set_analytics(option_analytics_engine)

    # Pick the 3-minute aggregator explicitly rather than relying on list
    # ordering in TickProcessor.__init__.
    _level_feed_aggregator = next(
        agg for agg in tick_processor.aggregators if agg.timeframe_minutes == 3
    )

    async def _feed_candle_aggregators(tick) -> None:
        # NOT tick_processor.process(tick) — that method itself publishes
        # MARKET_TICK, and this callback IS the MARKET_TICK subscriber;
        # calling it here would re-publish and re-trigger itself forever.
        #
        # Only the 3-minute aggregator feeds LevelEngine: its history/
        # active_levels dicts are keyed by instrument ONLY (not by
        # timeframe), so feeding multiple timeframes' CANDLE_CLOSED events
        # into it would interleave candles of different durations and
        # corrupt swing detection.
        await _level_feed_aggregator.process_tick(tick)

    event_bus.subscribe("MARKET_TICK", _feed_candle_aggregators)

    # If no broker has been explicitly activated yet but Upstox already
    # has a saved token, activate it automatically — this preserves
    # today's exact behavior (Upstox always connects on startup if a
    # token exists) under the new multi-broker model.
    #
    # This used to be a fire-and-forget asyncio.create_task(), so a broker
    # connect failure never took down the app. Now that it's awaited
    # directly, wrap it in try/except so a transient Upstox (or any
    # broker) connect failure at startup is logged but never prevents the
    # other ~20 engines below from starting.
    try:
        if active_broker.get_active_broker_id() is None and active_broker.is_broker_ready("upstox"):
            await active_broker.set_active_broker("upstox")
        elif active_broker.get_active_broker_id() and active_broker.get_active_provider():
            # A broker was already active from a previous run (persisted) —
            # (re)connect its feed now that the process has restarted.
            await active_broker.get_active_provider().connect_feed()
    except Exception:
        logger.exception("Failed to activate/reconnect broker feed at startup")
    # If neither branch applies (no broker ready/active), the app starts
    # with no live feed rather than silently defaulting to one.

    # Register position checkers so switching the active broker is
    # blocked while any of these has an open position/setup.
    active_broker.register_position_checker("CAS Dislocation", cas_dislocation_engine.get_open_position_blocker)
    active_broker.register_position_checker("Manual Trading", manual_trading_engine.get_open_position_blocker)
    active_broker.register_position_checker("OFAO", ofao_engine.get_open_position_blocker)

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

        if hasattr(footprint_processor, "stop"):
            footprint_processor.stop()

        if hasattr(mock_footprint_feed, "stop"):
            mock_footprint_feed.stop()

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

        if hasattr(ofao_engine, "stop"):
            ofao_engine.stop()

        if hasattr(market_breadth_engine, "stop"):
            market_breadth_engine.stop()

        if active_broker.get_active_provider() is not None:
            await active_broker.get_active_provider().disconnect_feed()

        # -----------------------------------------------------
        # Clear the module-level LevelEngine reference so it does not
        # outlive this lifespan (a later lifespan installs its own).
        # -----------------------------------------------------

        set_level_engine(None)

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
    footprint_router
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

app.include_router(
    ofao_router
)

app.include_router(
    backtest_router
)

app.include_router(
    executions_router
)

app.include_router(
    market_router
)

app.include_router(
    strategies_router
)

app.include_router(
    risk_summary_router
)

app.include_router(
    decisions_router
)

app.include_router(
    option_chain_router
)


# =============================================================
# HEALTH
# =============================================================

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
    }
