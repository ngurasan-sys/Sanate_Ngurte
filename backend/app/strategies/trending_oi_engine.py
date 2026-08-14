import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from backend.app.core.event_bus import event_bus
from backend.app.market_data.models import Tick
from backend.app.oi.models import OITick
from backend.app.strategies.trending_oi_price_action.engine import trending_oi_pa_engine


logger = logging.getLogger(__name__)

class SpotTrendingOIEngine:
    def __init__(self, underlying_symbol: str = "NIFTY"):
        self.underlying = underlying_symbol
        self.baseline_set = False

        self.current_interval = "5m"

        self.call_ltp_baseline = 0.0
        self.put_ltp_baseline = 0.0

        # State for the 15-strike basket
        # Strike -> CE/PE OI and LTP
        self.ce_state: Dict[float, Dict[str, float]] = {}
        self.pe_state: Dict[float, Dict[str, float]] = {}

        self.spot_price = 0.0
        self.strikes = []

        self.completed_rows = []
        self.current_row = self._create_empty_row()

    def _create_empty_row(self):
        return {
            "time": "",
            "ltp": 0.0,
            "dhb_price": False,
            "dlb_price": False,
            "chg_call_oi": 0.0,
            "chg_put_oi": 0.0,
            "diff_oi": 0.0,
            "direction": "NEUTRAL",
            "chg_direction": 0.0,
            "direction_pct": 0.0,
            "total_call_ltp": 0.0,
            "call_ltp_chg": 0.0,
            "ce_pe_ltp_chg": 0.0,
            "put_ltp_chg": 0.0,
            "total_put_ltp": 0.0,
            "net_pcr": 0.0,
            "dhb_oi": False,
            "dlb_oi": False,
            "sentiment": "Neutral",
            "ce_oi": 0,
            "pe_oi": 0,
            "crossover": "NO_CROSSOVER",
            "crossover_timestamp": None
        }

    def process_tick(self, tick: Tick):
        # We need to map Tick to our strike/CE/PE structures.
        # NIFTY spot tick vs options tick.

        # Determine if spot or option based on key (simplistic check for mock/integration)
        if tick.instrument == self.underlying or tick.instrument == f"NSE_INDEX|{self.underlying}":
            self.spot_price = tick.price
            # If not initialized strikes, initialize here
            if not self.strikes:
                self._initialize_strikes(self.spot_price)
            else:
                self._check_strike_shift(self.spot_price)

        elif "CE" in tick.instrument or "PE" in tick.instrument:
            # Parse strike and update
            # Simplified parsing
            try:
                # E.g. NIFTY241024C24500
                strike = float("".join([c for c in tick.instrument.split("C")[-1] if c.isdigit()]))
                if "CE" in tick.instrument or "C" in tick.instrument:
                    if strike not in self.ce_state:
                        self.ce_state[strike] = {"ltp": 0.0, "oi": 0, "base_oi": 0}
                    self.ce_state[strike]["ltp"] = tick.price
                    # We need OI from somewhere... if we don't have it on Tick, we assume it's passed somehow
                    # Upstox tick has volume, let's assume we can get OI from it for testing.
                    # Usually OI comes in marketFF
                elif "PE" in tick.instrument or "P" in tick.instrument:
                    if strike not in self.pe_state:
                        self.pe_state[strike] = {"ltp": 0.0, "oi": 0, "base_oi": 0}
                    self.pe_state[strike]["ltp"] = tick.price
            except Exception:
                pass

        self._calculate_current_row()

    def process_oi_tick(self, instrument: str, price: float, oi: float):
        if "CE" in instrument or "C" in instrument.split('|')[-1]:
             strike = float("".join([c for c in instrument if c.isdigit()]))
             if strike not in self.ce_state:
                 self.ce_state[strike] = {"ltp": price, "oi": oi, "base_oi": oi}
             else:
                 self.ce_state[strike]["oi"] = oi
                 self.ce_state[strike]["ltp"] = price
        elif "PE" in instrument or "P" in instrument.split('|')[-1]:
             strike = float("".join([c for c in instrument if c.isdigit()]))
             if strike not in self.pe_state:
                 self.pe_state[strike] = {"ltp": price, "oi": oi, "base_oi": oi}
             else:
                 self.pe_state[strike]["oi"] = oi
                 self.pe_state[strike]["ltp"] = price

        if not self.baseline_set:
            self._set_baseline()

        self._calculate_current_row()

    def _initialize_strikes(self, atm_price: float):
        # E.g., for NIFTY, step is 50
        step = 50
        atm = round(atm_price / step) * step
        self.strikes = [atm + (i - 7) * step for i in range(15)]
        self.atm = atm

    def _check_strike_shift(self, atm_price: float):
        step = 50
        new_atm = round(atm_price / step) * step

        if getattr(self, "atm", None) is not None and abs(new_atm - self.atm) >= step:
            self._initialize_strikes(atm_price)

    def _set_baseline(self):
        self.call_ltp_baseline = sum(s["ltp"] for s in self.ce_state.values())
        self.put_ltp_baseline = sum(s["ltp"] for s in self.pe_state.values())

        for state in self.ce_state.values():
            state["base_oi"] = state["oi"]

        for state in self.pe_state.values():
            state["base_oi"] = state["oi"]

        self.baseline_set = True

    def _calculate_current_row(self):
        row = self.current_row
        row["time"] = datetime.now().strftime("%H:%M:%S")
        row["ltp"] = self.spot_price

        chg_call_oi = sum((s["oi"] - s["base_oi"]) for k, s in self.ce_state.items() if k in self.strikes)
        chg_put_oi = sum((s["oi"] - s["base_oi"]) for k, s in self.pe_state.items() if k in self.strikes)

        row["chg_call_oi"] = chg_call_oi
        row["chg_put_oi"] = chg_put_oi

        diff_oi = chg_put_oi - chg_call_oi
        row["diff_oi"] = diff_oi

        prev_diff_oi = self.completed_rows[-1]["diff_oi"] if self.completed_rows else 0
        chg_direction = diff_oi - prev_diff_oi
        row["chg_direction"] = chg_direction

        if abs(prev_diff_oi) > 0:
            row["direction_pct"] = round((chg_direction / abs(prev_diff_oi)) * 100, 2)
        else:
            row["direction_pct"] = 0.0

        if chg_call_oi > 0:
            row["net_pcr"] = round(chg_put_oi / chg_call_oi, 2)
        else:
            row["net_pcr"] = 0.0

        if diff_oi > 0 and row["net_pcr"] >= 1.0:
            row["sentiment"] = "Bullish"
            row["direction"] = "BULLISH"
        elif diff_oi < 0 and row["net_pcr"] < 1.0:
            row["sentiment"] = "Bearish"
            row["direction"] = "BEARISH"
        else:
            row["sentiment"] = "Neutral"
            row["direction"] = "NEUTRAL"

        row["total_call_ltp"] = sum(s["ltp"] for s in self.ce_state.values() if s["ltp"] is not None)
        row["total_put_ltp"] = sum(s["ltp"] for s in self.pe_state.values() if s["ltp"] is not None)

        row["call_ltp_chg"] = row["total_call_ltp"] - self.call_ltp_baseline
        row["put_ltp_chg"] = row["total_put_ltp"] - self.put_ltp_baseline
        row["ce_pe_ltp_chg"] = row["call_ltp_chg"] + row["put_ltp_chg"]

        row["ce_oi"] = sum(s["oi"] for s in self.ce_state.values())
        row["pe_oi"] = sum(s["oi"] for s in self.pe_state.values())

        row["crossover"] = "NO_CROSSOVER"
        row["crossover_timestamp"] = None

        curr_call_oi = row["ce_oi"]
        curr_put_oi = row["pe_oi"]

        if self.completed_rows:
            # Find the last dominant side
            last_dominant = None
            for r in reversed(self.completed_rows):
                if r["ce_oi"] > r["pe_oi"]:
                    last_dominant = "CALL"
                    break
                elif r["pe_oi"] > r["ce_oi"]:
                    last_dominant = "PUT"
                    break

            if last_dominant == "CALL" and curr_put_oi > curr_call_oi:
                row["crossover"] = "BULLISH_CROSSOVER"
                row["crossover_timestamp"] = row["time"]
            elif last_dominant == "PUT" and curr_call_oi > curr_put_oi:
                row["crossover"] = "BEARISH_CROSSOVER"
                row["crossover_timestamp"] = row["time"]



        # D.H.B / D.L.B
        if self.completed_rows:
            max_p = max(r["ltp"] for r in self.completed_rows)
            min_p = min(r["ltp"] for r in self.completed_rows)
            row["dhb_price"] = self.spot_price > max_p
            row["dlb_price"] = self.spot_price < min_p

            max_oi = max(r["diff_oi"] for r in self.completed_rows)
            min_oi = min(r["diff_oi"] for r in self.completed_rows)
            row["dhb_oi"] = diff_oi > max_oi
            row["dlb_oi"] = diff_oi < min_oi

        self.current_row = row


class FutureTrendingOIEngine:
    def __init__(self, underlying_symbol: str = "NIFTY"):
        self.underlying = underlying_symbol
        self.completed_rows = []
        self.current_row = self._create_empty_row()

        self.prev_price = 0.0
        self.prev_oi = 0.0

    def _create_empty_row(self):
        return {
            "time": "",
            "futurePrice": 0.0,
            "oiChange": 0.0,
            "oiChangePercent": 0.0,
            "priceChange": 0.0,
            "classification": "NEUTRAL",
            "futureOi": 0,
            "volume": 0,
            "basis": 0.0,
            "basisChange": 0.0
        }

    def process_tick(self, price: float, oi: float, volume: float, spot_price: float):
        row = self.current_row
        row["time"] = datetime.now().strftime("%H:%M:%S")
        row["futurePrice"] = price

        price_change = price - self.prev_price if self.prev_price else 0
        oi_change = oi - self.prev_oi if self.prev_oi else 0

        row["priceChange"] = price_change
        row["oiChange"] = oi_change

        if self.prev_oi > 0:
            row["oiChangePercent"] = (oi_change / self.prev_oi) * 100

        row["futureOi"] = oi
        row["volume"] = volume
        row["basis"] = price - spot_price

        prev_basis = self.completed_rows[-1]["basis"] if self.completed_rows else 0
        row["basisChange"] = row["basis"] - prev_basis

        if price_change > 0 and oi_change > 0:
            row["classification"] = "LONG BUILDUP"
        elif price_change < 0 and oi_change > 0:
            row["classification"] = "SHORT BUILDUP"
        elif price_change < 0 and oi_change < 0:
            row["classification"] = "LONG UNWINDING"
        elif price_change > 0 and oi_change < 0:
            row["classification"] = "SHORT COVERING"

        self.prev_price = price
        self.prev_oi = oi
        self.current_row = row


class TrendingOIEngine:
    def __init__(self):
        self.spot_engine = SpotTrendingOIEngine()
        self.future_engine = FutureTrendingOIEngine()
        self.running = False
        self._publish_task = None

    def start(self):
        if self.running:
            return
        self.running = True

        # Subscribe to ticks
        event_bus.subscribe("MARKET_TICK", self._handle_market_tick)

        # We also need a periodic task to publish snap/updates to WS
        self._publish_task = asyncio.create_task(self._publish_loop())
        logger.info("TrendingOIEngine started")

    def stop(self):
        self.running = False
        if self._publish_task:
            self._publish_task.cancel()

    async def _handle_market_tick(self, tick: Tick):
        # Distribute tick to sub-engines
        self.spot_engine.process_tick(tick)

        # We need oi data. If tick has oi, we process it.
        # Upstox tick may need an extended schema for oi.
        oi = getattr(tick, "oi", 0) or 0

        if "FUT" in tick.instrument:
            # We need spot price for basis...
            self.future_engine.process_tick(tick.price, oi, tick.volume, self.spot_engine.spot_price)
        else:
            self.spot_engine.process_oi_tick(tick.instrument, tick.price, oi)

    async def _publish_loop(self):
        while self.running:
            await asyncio.sleep(1) # Publish at 1Hz

            row = {
                    "time": self.spot_engine.current_row["time"],
                    "differenceOi": self.spot_engine.current_row["diff_oi"],
                    "strength": max(0, min(100, int(abs(self.spot_engine.current_row.get("direction_pct", 0))))),
                    "direction": self.spot_engine.current_row["direction"],
                    "directionPercent": self.spot_engine.current_row["direction_pct"],
                    "sentiment": self.spot_engine.current_row["sentiment"],
                    "ceOi": self.spot_engine.current_row["ce_oi"],
                    "peOi": self.spot_engine.current_row["pe_oi"],
                    "changeCeOi": self.spot_engine.current_row["chg_call_oi"],
                    "changePeOi": self.spot_engine.current_row["chg_put_oi"],
                    "ltp": self.spot_engine.current_row["ltp"],
                    "crossover": self.spot_engine.current_row.get("crossover", "NO_CROSSOVER"),
                    "crossover_timestamp": self.spot_engine.current_row.get("crossover_timestamp")
                }

            # Inject execution state if available
            pa_state = trending_oi_pa_engine.positions.get("NIFTY FUT", {})
            row["execution_state"] = pa_state.get("position_state", "IDLE")
            row["trade_valid"] = pa_state.get("trade_valid", True)
            row["rejection_reason"] = pa_state.get("rejection_reason", "")
            row["time_filter_status"] = pa_state.get("time_filter_status", "VALID")
            row["distance_filter_status"] = pa_state.get("distance_filter_status", "VALID")
            row["vwap_supertrend_distance"] = pa_state.get("vwap_supertrend_distance", 0.0)

            spot_payload = {
                "type": "tick_update",
                "view": "spot_trending_oi",
                "underlying": "NIFTY",
                "row": row
            }

            future_payload = {
                "type": "tick_update",
                "view": "future_trending_oi",
                "underlying": "NIFTY",
                "row": self.future_engine.current_row
            }

            await event_bus.publish("trending_oi", spot_payload)
            await event_bus.publish("trending_oi", future_payload)

trending_oi_engine = TrendingOIEngine()
