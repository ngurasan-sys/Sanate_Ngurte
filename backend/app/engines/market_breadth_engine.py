import asyncio
import logging
from typing import Dict, List, Any
import redis
from backend.app.core.event_bus import event_bus

logger = logging.getLogger(__name__)

def calculate_eod_macro_trend(daily_data: List[Dict[str, float]]) -> Dict[str, Any]:
    """
    Analyzes the last 5 days of data to determine the macro trend.
    Uses the 3:35 PM CAS equilibrium price for accurate LTP deltas.
    """
    trend_sequence = []

    for day in daily_data:
        ltp_change = day['cas_close'] - day['prev_cas_close']

        if day['prev_total_oi'] == 0:
            continue

        oi_change_pct = (day['total_oi'] - day['prev_total_oi']) / day['prev_total_oi']

        # Rollover Filter
        if abs(oi_change_pct) > 1.0: # > 100% change
            trend_sequence.append("ROLLOVER_ANOMALY")
            continue

        if ltp_change > 0 and oi_change_pct > 0:
            trend_sequence.append("LONG_BUILDUP")
        elif ltp_change < 0 and oi_change_pct > 0:
            trend_sequence.append("SHORT_BUILDUP")
        elif ltp_change < 0 and oi_change_pct < 0:
            trend_sequence.append("LONG_UNWINDING")
        elif ltp_change > 0 and oi_change_pct < 0:
            trend_sequence.append("SHORT_COVERING")

    # Abstract the sequence for the clean frontend UI
    current_status = "NEUTRAL"
    if trend_sequence[-3:] == ["LONG_BUILDUP", "LONG_BUILDUP", "LONG_BUILDUP"]:
        current_status = "STRONG_BULLISH_CONFIRMED"

    return {
        "status": current_status,
        "last_3_days": trend_sequence[-3:] if len(trend_sequence) >= 3 else trend_sequence
    }

class MarketBreadthEngine:
    def __init__(self):
        self.running = False
        self._task = None
        # Use localhost for local dev without docker
        self.redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

    def start(self):
        if not self.running:
            self.running = True
            self._task = asyncio.create_task(self._worker())
            logger.info("MarketBreadthEngine started")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            logger.info("MarketBreadthEngine stopped")

    async def _worker(self):
        while self.running:
            try:
                # Simulate calculating 60-minute OI interpretation for top 6 Bank Nifty heavyweights
                heavyweight_sync = {
                    "HDFCBANK": {"status": "LONG_BUILDUP", "oi_chg": "+2.4%"},
                    "ICICIBANK": {"status": "LONG_BUILDUP", "oi_chg": "+1.8%"},
                    "SBIN": {"status": "SHORT_COVERING", "oi_chg": "-0.9%"},
                    "AXISBANK": {"status": "SHORT_BUILDUP", "oi_chg": "+1.2%"},
                    "KOTAKBANK": {"status": "LONG_UNWINDING", "oi_chg": "-1.5%"},
                    "INDUSINDBK": {"status": "LONG_BUILDUP", "oi_chg": "+0.8%"},
                }

                # Mock dummy EOD Data
                dummy_daily_data = [
                    {'cas_close': 100, 'prev_cas_close': 95, 'total_oi': 1000, 'prev_total_oi': 900},  # LONG_BUILDUP
                    {'cas_close': 105, 'prev_cas_close': 100, 'total_oi': 1100, 'prev_total_oi': 1000}, # LONG_BUILDUP
                    {'cas_close': 110, 'prev_cas_close': 105, 'total_oi': 1200, 'prev_total_oi': 1100}, # LONG_BUILDUP
                    {'cas_close': 115, 'prev_cas_close': 110, 'total_oi': 1300, 'prev_total_oi': 1200}, # LONG_BUILDUP
                    {'cas_close': 120, 'prev_cas_close': 115, 'total_oi': 1400, 'prev_total_oi': 1300}, # LONG_BUILDUP
                ]

                macro_trend = calculate_eod_macro_trend(dummy_daily_data)

                payload = {
                    "index": "BANKNIFTY",
                    "advance_decline": {"adv": 37, "dec": 13},
                    "heavyweight_sync": heavyweight_sync,
                    "macro_trend": macro_trend
                }

                import json
                try:
                    self.redis_client.setex("market_breadth_latest", 60, json.dumps(payload))
                except Exception as redis_e:
                    logger.warning(f"Failed to cache in Redis (is it running?): {redis_e}")

                # Publish to Event Bus for Websocket streaming
                await event_bus.publish("market_breadth", payload)

                # Sleep for a bit (simulating 1 minute or periodic updates)
                await asyncio.sleep(5) # Use 5 seconds for UI testing instead of 60
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in MarketBreadthEngine worker: {e}")
                await asyncio.sleep(5)

market_breadth_engine = MarketBreadthEngine()
