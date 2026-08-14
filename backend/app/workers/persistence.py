import asyncio
import logging
import duckdb
from typing import List, Any
import json
from backend.app.core.event_bus import event_bus

logger = logging.getLogger(__name__)

class AsyncPersistenceWorker:
    def __init__(self, db_path: str = "analytics.duckdb"):
        self.db_path = db_path
        self.queue = asyncio.Queue()
        self.batch_size = 100
        self.flush_interval = 1.0
        self.conn = duckdb.connect(self.db_path)
        self._init_db()
        event_bus.subscribe("persist_risk_event", self._enqueue_event)
        event_bus.subscribe("persist_execution", self._enqueue_event)
        event_bus.subscribe("persist_order_flow", self._enqueue_order_flow_event)

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS risk_events (
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                instrument VARCHAR,
                action VARCHAR,
                status VARCHAR
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                instrument VARCHAR,
                action VARCHAR,
                status VARCHAR
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS order_flow_snapshots (
                instrument_key VARCHAR,
                timestamp BIGINT,
                timeframe VARCHAR,
                classification_mode VARCHAR,
                trade_size BIGINT,
                buy_volume BIGINT,
                sell_volume BIGINT,
                bar_delta BIGINT,
                cvd BIGINT,
                state_json JSON
            )
        """)

    async def _enqueue_event(self, event_data: dict):
        await self.queue.put(("generic", event_data))

    async def _enqueue_order_flow_event(self, event_data: dict):
        await self.queue.put(("order_flow", event_data))

    async def run(self):
        logger.info("Starting Async Persistence Worker")
        batch = []
        while True:
            try:
                event = await asyncio.wait_for(self.queue.get(), timeout=self.flush_interval)
                batch.append(event)
                if len(batch) >= self.batch_size:
                    await self._flush_batch(batch)
                    batch = []
            except asyncio.TimeoutError:
                if batch:
                    await self._flush_batch(batch)
                    batch = []
            except asyncio.CancelledError:
                if batch:
                    await self._flush_batch(batch)
                break
            except Exception as e:
                logger.error(f"Error in persistence worker loop: {e}", exc_info=True)

    async def _flush_batch(self, batch: List[Any]):
        if not batch:
            return
        logger.debug(f"Flushing {len(batch)} events to DuckDB")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._sync_insert, batch)

    def _sync_insert(self, batch: List[Any]):
        try:
            risk_batch = []
            execution_batch = []
            order_flow_batch = []

            for event_type, event in batch:
                if event_type == "order_flow":
                    order_flow_batch.append((
                        event.get("instrument_key"),
                        event.get("timestamp"),
                        event.get("timeframe"),
                        event.get("classification_mode"),
                        event.get("trade_size"),
                        event.get("buy_volume"),
                        event.get("sell_volume"),
                        event.get("bar_delta"),
                        event.get("cvd"),
                        json.dumps(event)
                    ))
                elif "decision" in event and "status" in event:
                    decision = event["decision"]
                    risk_batch.append((decision.get("instrument"), decision.get("action"), event.get("status")))
                elif "status" in event and "action" in event:
                    execution_batch.append((event.get("instrument"), event.get("action"), event.get("status")))

            if risk_batch:
                self.conn.executemany(
                    "INSERT INTO risk_events (instrument, action, status) VALUES (?, ?, ?)",
                    risk_batch
                )
            if execution_batch:
                self.conn.executemany(
                    "INSERT INTO executions (instrument, action, status) VALUES (?, ?, ?)",
                    execution_batch
                )
            if order_flow_batch:
                self.conn.executemany(
                    """
                    INSERT INTO order_flow_snapshots (
                        instrument_key, timestamp, timeframe, classification_mode,
                        trade_size, buy_volume, sell_volume, bar_delta, cvd, state_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    order_flow_batch
                )
        except Exception as e:
            logger.error(f"Failed to insert batch into DuckDB: {e}", exc_info=True)

persistence_worker = AsyncPersistenceWorker()
