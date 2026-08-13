import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.greeks import router as greeks_router

from backend.app.core.event_bus import event_bus
from backend.app.api.websockets import router as websocket_router
from backend.app.workers.persistence import persistence_worker

import backend.app.engines.decision
import backend.app.engines.risk
import backend.app.engines.execution

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the event bus and persistence worker when the loop is running
    event_bus.start()
    persistence_task = asyncio.create_task(persistence_worker.run())
    logger.info("Application starting up, persistence worker started.")
    yield
    persistence_task.cancel()
    try:
        await persistence_task
    except asyncio.CancelledError:
        pass
    logger.info("Application shutting down, persistence worker stopped.")

app = FastAPI(title="Algo Trading Workstation", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(websocket_router)
app.include_router(greeks_router)

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
