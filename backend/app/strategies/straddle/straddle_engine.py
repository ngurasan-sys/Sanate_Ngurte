import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
import math
from backend.app.core.event_bus import event_bus
from backend.app.market_data.models import Tick

logger = logging.getLogger(__name__)

def check_straddle_regime(call_oi: float, put_oi: float) -> str:
    max_oi = max(call_oi, put_oi)
    if max_oi == 0:
        return "UNCERTAIN"

    diff_pct = abs(call_oi - put_oi) / max_oi

    # If OI difference is very tight (e.g., < 20% difference), sellers are balanced
    if diff_pct < 0.20:
        return "NON_DIRECTIONAL_STRADDLE_SELL"
    # Directional trades require > 40-50% difference
    elif diff_pct > 0.45:
        return "DIRECTIONAL_TRENDING"
    else:
        return "NO_TRADE_ZONE"

class StraddleTracker:
    def __init__(self, atm_strike: float):
        self.atm_strike = atm_strike
        self.straddle_series = [] # Stores {timestamp, combined_ltp, volume, vwap, ema_20}

        # internal tracking for VWAP
        self.cumulative_volume = 0.0
        self.cumulative_price_volume = 0.0

        # internal tracking for EMA
        self.ema_20: Optional[float] = None

    def calculate_vwap(self) -> float:
        if self.cumulative_volume == 0:
            return 0.0
        return self.cumulative_price_volume / self.cumulative_volume

    def calculate_ema(self, new_price: float, period: int = 20) -> float:
        if self.ema_20 is None:
            self.ema_20 = new_price
        else:
            multiplier = 2 / (period + 1)
            self.ema_20 = (new_price - self.ema_20) * multiplier + self.ema_20
        return self.ema_20

    def process_tick(self, ce_data: dict, pe_data: dict, timestamp: datetime) -> dict:
        combined_premium = ce_data.get('ltp', 0.0) + pe_data.get('ltp', 0.0)
        combined_volume = ce_data.get('volume', 0.0) + pe_data.get('volume', 0.0)

        self.cumulative_volume += combined_volume
        self.cumulative_price_volume += (combined_premium * combined_volume)

        current_vwap = self.calculate_vwap()
        current_ema = self.calculate_ema(combined_premium, period=20)

        # Append to series
        entry = {
            "timestamp": timestamp.strftime("%H:%M:%S"),
            "combined_premium": combined_premium,
            "volume": combined_volume,
            "vwap": current_vwap,
            "ema_20": current_ema
        }
        self.straddle_series.append(entry)

        # Trailing Stop Logic for Short Straddle
        # Usually EXIT if premium goes above VWAP (since we sold it, we want it low)
        signal = "HOLD_SHORT" if (current_vwap == 0.0 or combined_premium < current_vwap) else "EXIT_ABOVE_VWAP"

        return {
            "combined_premium": combined_premium,
            "vwap": current_vwap,
            "ema_20": current_ema,
            "signal": signal
        }

class StraddleEngine:
    def __init__(self, underlying_symbol: str = "NIFTY"):
        self.underlying = underlying_symbol
        self.running = False
        self._publish_task = None

        self.spot_price = 0.0
        self.ce_state: Dict[float, dict] = {} # strike -> {ltp, oi, volume}
        self.pe_state: Dict[float, dict] = {}

        self.tracker: Optional[StraddleTracker] = None
        self.current_state = {}

    def start(self):
        if self.running:
            return
        self.running = True
        event_bus.subscribe("MARKET_TICK", self._handle_market_tick)
        self._publish_task = asyncio.create_task(self._publish_loop())
        logger.info("StraddleEngine started")

    def stop(self):
        self.running = False
        if self._publish_task:
            self._publish_task.cancel()

    def _get_atm_strike(self, price: float) -> float:
        # Assuming NIFTY 50 step
        step = 50
        return round(price / step) * step

    async def _handle_market_tick(self, tick: Tick):
        if tick.instrument == self.underlying or tick.instrument == f"{self.underlying} 50":
            self.spot_price = tick.price
        elif "CE" in tick.instrument or "C" in tick.instrument.split('|')[-1]:
            try:
                strike_str = "".join([c for c in tick.instrument if c.isdigit()])
                if strike_str:
                    strike = float(strike_str)
                    if strike not in self.ce_state:
                        self.ce_state[strike] = {"ltp": 0.0, "oi": 0.0, "volume": 0.0}
                    self.ce_state[strike]["ltp"] = tick.price
                    if tick.volume:
                        self.ce_state[strike]["volume"] = tick.volume
                    if hasattr(tick, "oi") and tick.oi:
                        self.ce_state[strike]["oi"] = tick.oi
            except Exception:
                pass
        elif "PE" in tick.instrument or "P" in tick.instrument.split('|')[-1]:
            try:
                strike_str = "".join([c for c in tick.instrument if c.isdigit()])
                if strike_str:
                    strike = float(strike_str)
                    if strike not in self.pe_state:
                        self.pe_state[strike] = {"ltp": 0.0, "oi": 0.0, "volume": 0.0}
                    self.pe_state[strike]["ltp"] = tick.price
                    if tick.volume:
                        self.pe_state[strike]["volume"] = tick.volume
                    if hasattr(tick, "oi") and tick.oi:
                        self.pe_state[strike]["oi"] = tick.oi
            except Exception:
                pass

        if self.spot_price > 0:
            atm = self._get_atm_strike(self.spot_price)
            if self.tracker is None or self.tracker.atm_strike != atm:
                self.tracker = StraddleTracker(atm)

            ce_data = self.ce_state.get(atm, {})
            pe_data = self.pe_state.get(atm, {})

            call_oi = ce_data.get('oi', 0.0)
            put_oi = pe_data.get('oi', 0.0)

            regime = check_straddle_regime(call_oi, put_oi)

            # Process tick for tracker
            if ce_data and pe_data:
                tracker_out = self.tracker.process_tick(ce_data, pe_data, tick.timestamp)

                self.current_state = {
                    "timestamp": tick.timestamp.strftime("%H:%M:%S"),
                    "underlying": self.spot_price,
                    "atm_strike": atm,
                    "market_regime": regime,
                    "straddle_data": {
                        "current_premium": tracker_out["combined_premium"],
                        "vwap": tracker_out["vwap"],
                        "ema_20": tracker_out["ema_20"],
                        "action": tracker_out["signal"],
                        "trailing_sl": tracker_out["vwap"]
                    }
                }

    async def _publish_loop(self):
        while self.running:
            await asyncio.sleep(1) # Broadcast at 1Hz
            if self.current_state:
                await event_bus.publish("straddle", self.current_state)

straddle_engine = StraddleEngine()
