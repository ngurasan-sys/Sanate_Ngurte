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
        event_bus.subscribe("persist_ofao_setup", self._enqueue_ofao_event)

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
        # One row per OFAO state *transition* (see engine.py's
        # _update_snapshot — it only publishes persist_ofao_setup when
        # the state actually changed), not per evaluation cycle — the
        # trade journal (spec §27) this feeds needs the setup's history,
        # not a 500ms-resolution flood.
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ofao_setups (
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                instrument_key VARCHAR,
                underlying VARCHAR,
                setup_id VARCHAR,
                state VARCHAR,
                direction VARCHAR,
                location_price DOUBLE,
                absorption_strength DOUBLE,
                last_price DOUBLE,
                state_json JSON
            )
        """)

    async def _enqueue_event(self, event_data: dict):
        await self.queue.put(("generic", event_data))

    async def _enqueue_order_flow_event(self, event_data: dict):
        await self.queue.put(("order_flow", event_data))

    async def _enqueue_ofao_event(self, event_data: dict):
        await self.queue.put(("ofao_setup", event_data))

    async def run(self):
        logger.info("Starting Async Persistence Worker")
        # Rebind the queue to whichever event loop is running this call.
        # Reusing a Queue created under a previous (now-closed) event loop
        # raises RuntimeError on every get(), which without this reset
        # busy-loops the except-Exception branch below indefinitely.
        self.queue = asyncio.Queue()
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
                await asyncio.sleep(self.flush_interval)

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
            ofao_batch = []

            for item in batch:
                if isinstance(item, tuple):
                    event_type, event = item
                else:
                    event_type, event = "generic", item

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
                elif event_type == "ofao_setup":
                    ofao_batch.append((
                        event.get("instrument_key"),
                        event.get("underlying"),
                        event.get("setup_id"),
                        event.get("state"),
                        event.get("direction"),
                        event.get("location_price"),
                        event.get("absorption_strength"),
                        event.get("last_price"),
                        json.dumps(event, default=str),
                    ))
                elif isinstance(event, dict) and "decision" in event and "status" in event:
                    decision = event["decision"]
                    risk_batch.append((decision.get("instrument"), decision.get("action"), event.get("status")))
                elif isinstance(event, dict) and "status" in event and "action" in event:
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
            if ofao_batch:
                self.conn.executemany(
                    """
                    INSERT INTO ofao_setups (
                        instrument_key, underlying, setup_id, state, direction,
                        location_price, absorption_strength, last_price, state_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ofao_batch
                )
        except Exception as e:
            logger.error(f"Failed to insert batch into DuckDB: {e}", exc_info=True)

persistence_worker = AsyncPersistenceWorker()
