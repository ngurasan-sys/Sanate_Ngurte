from .event_bus import event_bus
from .db import DuckDBManager
from .websocket import ConnectionManager
import logging
import json

logger = logging.getLogger(__name__)

class DatabaseListeners:
    def __init__(self, db_manager: DuckDBManager, ws_manager: ConnectionManager):
        self.db_manager = db_manager
        self.ws_manager = ws_manager

    def start(self):
        event_bus.subscribe("LEVEL_CREATED", self.on_level_created)
        event_bus.subscribe("STRATEGY_SIGNAL", self.on_strategy_signal)
        # Note: We also listen to push to websocket
        event_bus.subscribe("LEVEL_CREATED", self.push_level_ws)

    async def on_level_created(self, level_data: dict):
        try:
            self.db_manager.execute("""
                INSERT INTO levels (
                    level_id, instrument, price, zone_low, zone_high,
                    level_type, timeframe, strength, confidence, touch_count,
                    rejection_count, breakout_count, volume_confirmation,
                    liquidity_score, distance_from_price, age, source,
                    created_at, updated_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                level_data['level_id'], level_data['instrument'], level_data['price'],
                level_data['zone_low'], level_data['zone_high'], level_data['level_type'],
                level_data['timeframe'], level_data['strength'], level_data['confidence'],
                level_data['touch_count'], level_data['rejection_count'], level_data['breakout_count'],
                level_data['volume_confirmation'], level_data['liquidity_score'],
                level_data['distance_from_price'], level_data['age'], level_data['source'],
                level_data['created_at'], level_data['updated_at'], level_data['active']
            ))
        except Exception as e:
            logger.error(f"Error saving level to DB: {e}")

    async def on_strategy_signal(self, signal: dict):
        try:
            self.db_manager.execute("""
                INSERT INTO level_strategy_signals (
                    signal_id, strategy_id, instrument, timestamp, direction,
                    level_id, confidence, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal['signal_id'], signal['strategy_id'], signal['instrument'],
                signal['timestamp'], signal['direction'], signal['level_id'],
                signal['confidence'], json.dumps({"evidence": signal.get("evidence")})
            ))
        except Exception as e:
            logger.error(f"Error saving strategy signal to DB: {e}")

    async def push_level_ws(self, level_data: dict):
        await self.ws_manager.broadcast({
            "type": "LEVEL_CREATED",
            "data": level_data
        }, "levels")
