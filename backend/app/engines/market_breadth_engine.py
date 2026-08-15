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

REDIS_RETRY_COOLDOWN_SECONDS = 30

class MarketBreadthEngine:
    def __init__(self):
        self.running = False
        self._task = None
        # Use localhost for local dev without docker
        self.redis_client = redis.Redis(
            host='localhost', port=6379, decode_responses=True,
            socket_connect_timeout=1, socket_timeout=1,
        )
        self._redis_unavailable_since = None

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
                # No live per-stock OI/breadth data source is wired up yet
                # (this would need real 60-minute OI history for the Bank
                # Nifty heavyweights and real EOD CAS close/OI data). Report
                # that honestly instead of publishing fabricated numbers.
                payload = {
                    "index": "BANKNIFTY",
                    "sufficient_data": False,
                    "reason": "No live per-stock OI/breadth data source is wired up yet.",
                }

                import json
                now = asyncio.get_event_loop().time()
                cooling_down = (
                    self._redis_unavailable_since is not None
                    and now - self._redis_unavailable_since < REDIS_RETRY_COOLDOWN_SECONDS
                )
                if not cooling_down:
                    # Cheap, cancellable reachability probe first: redis-py's own
                    # client can spend many seconds retrying internally once a
                    # blocking call is handed to a thread (that thread can't be
                    # killed on cancellation), so only touch redis-py once we
                    # know a TCP connection is actually possible.
                    reachable = False
                    try:
                        _, writer = await asyncio.wait_for(
                            asyncio.open_connection(
                                self.redis_client.connection_pool.connection_kwargs["host"],
                                self.redis_client.connection_pool.connection_kwargs["port"],
                            ),
                            timeout=0.5,
                        )
                        writer.close()
                        reachable = True
                    except Exception:
                        reachable = False

                    if reachable:
                        try:
                            await asyncio.to_thread(
                                self.redis_client.setex,
                                "market_breadth_latest", 60, json.dumps(payload),
                            )
                            self._redis_unavailable_since = None
                        except Exception as redis_e:
                            self._redis_unavailable_since = now
                            logger.warning(f"Failed to cache in Redis (is it running?): {redis_e}")
                    else:
                        self._redis_unavailable_since = now
                        logger.warning("Failed to cache in Redis (is it running?): unreachable")

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
