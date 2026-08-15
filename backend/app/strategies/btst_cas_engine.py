import asyncio
import logging
from datetime import datetime, time
from typing import Dict

from backend.app.core.event_bus import event_bus

logger = logging.getLogger(__name__)

def evaluate_btst_signal(futures_trend: str, post_1pm_oi: dict, cas_market_state: dict) -> Dict:
    """
    Evaluates the BTST setup. Execution is strictly bound to the 3:35 PM - 3:40 PM window.
    """
    current_time = datetime.now().time()
    cas_resolution_time = time(15, 35) # 3:35 PM (Cash Market Close Published)
    fo_close_time = time(15, 40)       # 3:40 PM (F&O Market Close)

    # 1. Timing Gatekeeper
    if not (cas_resolution_time <= current_time < fo_close_time):
         return {
             "status": "WAITING",
             "message": "Awaiting CAS Equilibrium Window (3:35 PM - 3:40 PM)",
             "signal": "NONE",
             "pillar_macro": False,
             "pillar_micro": False,
             "pillar_cas": False,
             "futures_trend": futures_trend,
             "post_1pm_oi": post_1pm_oi,
             "cas_market_state": cas_market_state,
             "current_time_str": current_time.strftime("%H:%M:%S")
         }

    # 2. Pillar 1: Futures Macro Context
    # Valid conditions: "SHORT_BUILDUP" or "LONG_UNWINDING"
    is_macro_bearish = futures_trend in ["SHORT_BUILDUP", "LONG_UNWINDING"]

    # 3. Pillar 2: Intraday Micro Shift (Post 1:00 PM)
    # Bearish confirmation: Heavy Call writing + Put exiting
    is_micro_bearish = (post_1pm_oi['call_oi_change'] > 2000000 and
                        post_1pm_oi['put_oi_change'] < -1000000)

    # 4. Pillar 3: CAS Price Action
    # Bearish confirmation: Final CAS equilibrium price settles near the day's low (bottom 15% of range)
    cas_price = cas_market_state['equilibrium_price']
    day_high = cas_market_state['day_high']
    day_low = cas_market_state['day_low']

    is_closing_low = False
    if day_high > day_low:
        closing_percentile = (cas_price - day_low) / (day_high - day_low)
        is_closing_low = closing_percentile <= 0.15

    # Signal Generation
    if is_macro_bearish and is_micro_bearish and is_closing_low:
        return {
             "status": "ACTIVE_WINDOW",
             "message": "Strong Bearish Conviction Confirmed.",
             "signal": "EXECUTE_BTST_PUT",
             "deadline": "15:39:00",
             "pillar_macro": is_macro_bearish,
             "pillar_micro": is_micro_bearish,
             "pillar_cas": is_closing_low,
             "futures_trend": futures_trend,
             "post_1pm_oi": post_1pm_oi,
             "cas_market_state": cas_market_state,
             "current_time_str": current_time.strftime("%H:%M:%S")
        }

    return {
         "status": "ACTIVE_WINDOW",
         "message": "Conditions not met for overnight carry.",
         "signal": "NEUTRAL",
         "pillar_macro": is_macro_bearish,
         "pillar_micro": is_micro_bearish,
         "pillar_cas": is_closing_low,
         "futures_trend": futures_trend,
         "post_1pm_oi": post_1pm_oi,
         "cas_market_state": cas_market_state,
         "current_time_str": current_time.strftime("%H:%M:%S")
    }

class BTSTCASEngine:
    def __init__(self):
        self._running = False
        self._task = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("BTST CAS Engine started.")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("BTST CAS Engine stopped.")

    async def _run_loop(self):
        while self._running:
            try:
                # No live futures OI trend, post-1PM OI delta, or CAS
                # equilibrium price feed is wired up yet — report that
                # honestly instead of publishing fabricated signal state.
                result = {
                    "status": "INSUFFICIENT_DATA",
                    "message": "No live futures OI / post-1PM OI / CAS equilibrium data source is wired up yet.",
                    "signal": "NONE",
                    "current_time_str": datetime.now().time().strftime("%H:%M:%S"),
                }

                # Emit via Event Bus
                await event_bus.publish("btst_cas_stream", result)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in BTST CAS Engine loop: {e}")

            await asyncio.sleep(5)

btst_cas_engine = BTSTCASEngine()
