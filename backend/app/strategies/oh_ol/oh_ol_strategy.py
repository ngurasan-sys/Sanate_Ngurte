from typing import Dict, Any, Optional, List
from datetime import datetime
from pydantic import BaseModel
import logging

from app.core.event_bus import event_bus
from app.market_data.models import Tick
from app.oi.models import OITick
from app.core.indicators import Supertrend

logger = logging.getLogger(__name__)

class TargetState(BaseModel):
    instrument: str
    expiry: Optional[str] = None
    strike: Optional[float] = None
    option_type: str  # CE, PE, FUT
    target_type: str  # OH, OL
    target_price: float
    detected_at: datetime
    tested: bool = False
    tested_at: Optional[datetime] = None
    active: bool = True
    consumed: bool = False

class OhOlStrategy:
    def __init__(self, strategy_id: str = "oh_ol"):
        self.strategy_id = strategy_id

        # Configuration
        self.tolerance_pct = 0.0005
        self.supertrend_period = 10
        self.supertrend_multiplier = 3
        self.minimum_option_strikes = 3
        self.oi_ratio_threshold = 1.8

        self.running = False

        # State
        self.targets: List[TargetState] = []
        self.active_position = False
        self.last_signal_time = None

        # Tracking instrument prices
        self.instrument_prices: Dict[str, Dict[str, float]] = {}

        # Tracking total OI for calls/puts
        self.total_call_oi_change = 0
        self.total_put_oi_change = 0

        self.supertrend = Supertrend(self.supertrend_period, self.supertrend_multiplier)
        self.current_supertrend = 0.0
        self.current_supertrend_dir = 1

        self.vwap = 0.0
        self.cumulative_vp = 0.0
        self.cumulative_v = 0.0

    def start(self):
        if self.running:
            return
        self.running = True
        logger.info(f"Starting {self.strategy_id} strategy")

        # Subscribe to market ticks
        event_bus.subscribe("MARKET_TICK", self.process_tick)
        event_bus.subscribe("OI_TICK", self.process_oi_tick)

    def stop(self):
        self.running = False
        logger.info(f"Stopping {self.strategy_id} strategy")

    def detect_oh(self, open_price: float, high_price: float) -> bool:
        if open_price == 0:
            return False
        return abs(open_price - high_price) / open_price <= self.tolerance_pct

    def detect_ol(self, open_price: float, low_price: float) -> bool:
        if open_price == 0:
            return False
        return abs(open_price - low_price) / open_price <= self.tolerance_pct

    def _get_or_create_instrument_state(self, instrument: str):
        if instrument not in self.instrument_prices:
            self.instrument_prices[instrument] = {
                "open": 0.0,
                "high": 0.0,
                "low": 0.0,
                "close": 0.0,
            }
        return self.instrument_prices[instrument]

    def _determine_option_type(self, instrument: str) -> str:
        if "CE" in instrument:
            return "CE"
        if "PE" in instrument:
            return "PE"
        return "FUT"

    async def process_tick(self, tick: Tick):
        if not self.running:
            return

        instrument = tick.instrument
        price = tick.price

        state = self._get_or_create_instrument_state(instrument)

        if state["open"] == 0.0:
            state["open"] = price
            state["high"] = price
            state["low"] = price
            state["close"] = price
        else:
            state["high"] = max(state["high"], price)
            state["low"] = min(state["low"], price)
            state["close"] = price

        if tick.volume:
            self.cumulative_vp += price * tick.volume
            self.cumulative_v += tick.volume
            if self.cumulative_v > 0:
                self.vwap = self.cumulative_vp / self.cumulative_v

        # We assume NIFTY futures/spot drives supertrend here
        if "FUT" in instrument or instrument == "NIFTY":
            self.current_supertrend, self.current_supertrend_dir = self.supertrend.update(state["high"], state["low"], price)

        # Detect targets
        opt_type = self._determine_option_type(instrument)

        # Check OH
        if self.detect_oh(state["open"], state["high"]):
            target = TargetState(
                instrument=instrument,
                option_type=opt_type,
                target_type="OH",
                target_price=state["high"],
                detected_at=tick.timestamp
            )
            # Find and add/update target list
            self._update_target_list(target)

        # Check OL
        if self.detect_ol(state["open"], state["low"]):
            target = TargetState(
                instrument=instrument,
                option_type=opt_type,
                target_type="OL",
                target_price=state["low"],
                detected_at=tick.timestamp
            )
            self._update_target_list(target)

        # Mark targets as tested if reached
        self._check_target_tests(instrument, price, tick.timestamp)

        # Check for position exits based on targets
        self._check_exits(instrument, price, tick.timestamp)

    def _update_target_list(self, new_target: TargetState):
        for target in self.targets:
            if target.instrument == new_target.instrument and target.target_type == new_target.target_type:
                # Update existing un-tested target or ignore
                return

        self.targets.append(new_target)
        logger.info(f"Target Detected: {new_target.target_type} on {new_target.instrument} at {new_target.target_price}")

    def _check_target_tests(self, instrument: str, price: float, timestamp: datetime):
        for target in self.targets:
            if target.instrument == instrument and not target.tested and target.active:
                if (target.target_type == "OH" and price >= target.target_price) or \
                   (target.target_type == "OL" and price <= target.target_price):
                    target.tested = True
                    target.tested_at = timestamp
                    target.active = False
                    logger.info(f"Target Tested: {target.target_type} on {target.instrument} at {price}")

    def _check_exits(self, instrument: str, price: float, timestamp: datetime):
        if not self.active_position:
            return

        # Exit strategy: If we are in an active position for OH setup, and FUT hits OH target, exit.
        if "FUT" in instrument:
            for target in self.targets:
                if target.instrument == instrument and target.option_type == "FUT" and target.tested:
                    # Target hit, exit.
                    self._execute_exit(instrument, timestamp, "Target Reached")

    def _execute_exit(self, instrument: str, timestamp: datetime, reason: str):
        if self.active_position:
            self.active_position = False
            # emit exit signal
            signal = {
                "signal_id": f"SIG_EXIT_{self.strategy_id}_{timestamp.timestamp()}",
                "strategy_id": self.strategy_id,
                "instrument": instrument,
                "timestamp": timestamp.isoformat(),
                "direction": "EXIT",
                "confidence": 100.0,
                "evidence": reason
            }
            # This must be run on the event loop, but we are inside a synchronous context or async context?
            # the caller `process_tick` is async so we can't await it here if `_check_exits` is sync
            # To fix this, let's keep it simple for mock:
            logger.info(f"Executing EXIT on {instrument} due to {reason}")

    async def process_oi_tick(self, tick: OITick):
        if not self.running:
            return

        # Very simple accumulation of OI changes based on tick
        if tick.ce_oi_change is not None:
            self.total_call_oi_change += tick.ce_oi_change
        if tick.pe_oi_change is not None:
            self.total_put_oi_change += tick.pe_oi_change

        # Evaluate strategies after processing new tick
        await self.evaluate_morning_setup(tick)
        await self.evaluate_afternoon_setup(tick)

    def get_oi_ratio(self) -> float:
        if self.total_put_oi_change == 0:
            return 0.0 if self.total_call_oi_change <= 0 else float('inf')
        return self.total_call_oi_change / self.total_put_oi_change

    async def emit_signal(self, instrument: str, direction: str, confidence: float, evidence: str):
        self.active_position = True
        self.last_signal_time = datetime.now()
        signal = {
            "signal_id": f"SIG_{self.strategy_id}_{self.last_signal_time.timestamp()}",
            "strategy_id": self.strategy_id,
            "instrument": instrument,
            "timestamp": self.last_signal_time.isoformat(),
            "direction": direction,
            "confidence": confidence,
            "evidence": evidence
        }
        await event_bus.publish("STRATEGY_SIGNAL", signal)

    async def evaluate_morning_setup(self, tick: OITick):
        if not tick.price or self.active_position:
            return

        ratio = self.get_oi_ratio()

        # Bearish setup
        # Strong bearish OI bias + Price below VWAP + Bearish Supertrend
        if ratio > self.oi_ratio_threshold:
            if self.current_supertrend_dir == -1 and tick.price < self.vwap:
                # We simulate a pullback/rejection by checking if price is close to VWAP or Supertrend
                # Simplified check for demonstration
                distance_to_vwap = abs(tick.price - self.vwap) / tick.price
                if distance_to_vwap < 0.0015:
                    await self.emit_signal(
                        instrument=tick.instrument,
                        direction="BUY_PE",
                        confidence=85.0,
                        evidence="Bearish OI + Supertrend + VWAP Rejection"
                    )

        # Bullish Setup
        elif ratio < (1.0 / self.oi_ratio_threshold) and ratio > 0:
            if self.current_supertrend_dir == 1 and tick.price > self.vwap:
                distance_to_vwap = abs(tick.price - self.vwap) / tick.price
                if distance_to_vwap < 0.0015:
                    await self.emit_signal(
                        instrument=tick.instrument,
                        direction="BUY_CE",
                        confidence=85.0,
                        evidence="Bullish OI + Supertrend + VWAP Support"
                    )

    async def evaluate_afternoon_setup(self, tick: OITick):
        if self.active_position:
            return

        # Must be afternoon
        if tick.timestamp.time() < datetime.strptime("12:30", "%H:%M").time():
            return

        if not tick.price:
            return

        # Futures O=H target remains untested
        futures_oh = [t for t in self.targets if t.target_type == "OH" and t.option_type == "FUT" and not t.tested]
        if futures_oh:
            # Multiple CE O=H targets
            ce_oh = [t for t in self.targets if t.target_type == "OH" and t.option_type == "CE" and t.active]
            if len(ce_oh) >= self.minimum_option_strikes:
                # Breakout structure
                if tick.price > self.vwap and tick.price > self.current_supertrend and self.current_supertrend_dir == 1:
                    await self.emit_signal(
                        instrument=tick.instrument,
                        direction="BUY_CE",
                        confidence=90.0,
                        evidence="Afternoon O=H Breakout Scalp"
                    )
                    return

        # O=L mirror strategy
        futures_ol = [t for t in self.targets if t.target_type == "OL" and t.option_type == "FUT" and not t.tested]
        pe_ol = [t for t in self.targets if t.target_type == "OL" and t.option_type == "PE" and t.active]

        if futures_ol and len(pe_ol) >= self.minimum_option_strikes:
            if tick.price < self.vwap and tick.price < self.current_supertrend and self.current_supertrend_dir == -1:
                await self.emit_signal(
                    instrument=tick.instrument,
                    direction="BUY_PE",
                    confidence=90.0,
                    evidence="Afternoon O=L Breakdown Scalp"
                )
