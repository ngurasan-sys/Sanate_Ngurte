import duckdb
import os
import threading

class DuckDBManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DuckDBManager, cls).__new__(cls)
                cls._instance._init_db()
            return cls._instance

    def _init_db(self):
        db_path = os.getenv("DUCKDB_PATH", "sanate.duckdb")
        self.conn = duckdb.connect(db_path)
        self.setup_tables()

    def setup_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS levels (
                level_id VARCHAR PRIMARY KEY,
                instrument VARCHAR,
                price DOUBLE,
                zone_low DOUBLE,
                zone_high DOUBLE,
                level_type VARCHAR,
                timeframe VARCHAR,
                strength DOUBLE,
                confidence DOUBLE,
                touch_count INTEGER,
                rejection_count INTEGER,
                breakout_count INTEGER,
                volume_confirmation BOOLEAN,
                liquidity_score DOUBLE,
                distance_from_price DOUBLE,
                age INTEGER,
                source VARCHAR,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                active BOOLEAN
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS level_events (
                event_id VARCHAR PRIMARY KEY,
                level_id VARCHAR,
                event_type VARCHAR,
                timestamp TIMESTAMP,
                price DOUBLE,
                details JSON
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS level_strategy_signals (
                signal_id VARCHAR PRIMARY KEY,
                strategy_id VARCHAR,
                instrument VARCHAR,
                timestamp TIMESTAMP,
                direction VARCHAR,
                level_id VARCHAR,
                confidence DOUBLE,
                details JSON
            )
        """)

    def execute(self, query: str, parameters=None):
        if parameters:
            return self.conn.execute(query, parameters)
        return self.conn.execute(query)

    def fetchall(self, query: str, parameters=None):
        if parameters:
            return self.conn.execute(query, parameters).fetchall()
        return self.conn.execute(query).fetchall()

    def close(self):
        self.conn.close()

db_manager = DuckDBManager()
