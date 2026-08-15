from typing import Dict, Any, Optional
from datetime import datetime
from backend.app.core.event_bus import event_bus
from enum import Enum

class GapDirection(Enum):
    GAP_UP = "GAP UP"
    GAP_DOWN = "GAP DOWN"
    FLAT = "FLAT"

class GapOpeningStrategies:
    def __init__(self, strategy_id: str = "gap_opening_strategies"):
        self.strategy_id = strategy_id

        # Strategy internal state
        self.market_phase = "WAITING"
        self.tier_1_status = "WAITING"
        self.tier_2_status = "WAITING"
        self.active_position = False

        self.previous_close = 0.0
        self.today_open = 0.0
        self.gap_points = 0.0
        self.gap_percent = 0.0
        self.gap_direction = GapDirection.FLAT

    def _update_gap_stats(self, prev_close: float, current_open: float):
        if prev_close == 0:
            return

        self.previous_close = prev_close
        self.today_open = current_open
        self.gap_points = self.today_open - self.previous_close
        self.gap_percent = (self.gap_points / self.previous_close) * 100

        if self.gap_percent > 0.1: # Threshold for gap up
            self.gap_direction = GapDirection.GAP_UP
        elif self.gap_percent < -0.1:
            self.gap_direction = GapDirection.GAP_DOWN
        else:
            self.gap_direction = GapDirection.FLAT

    async def evaluate(self, tick: Dict[str, Any], context: Dict[str, Any] = None):
        """
        Evaluate market conditions for the Gap Opening strategy.
        """
        if context is None:
            context = {}

        timestamp_val = tick.get("timestamp")
        if not timestamp_val:
            return

        if isinstance(timestamp_val, str):
            try:
                dt = datetime.fromisoformat(timestamp_val.replace('Z', '+00:00'))
                time_str = dt.strftime("%H:%M:%S")
            except Exception:
                time_str = "00:00:00"
        else:
            time_str = timestamp_val.strftime("%H:%M:%S")

        # Update gap stats if missing and available in context
        if self.today_open == 0.0 and context.get("today_open"):
            self._update_gap_stats(context.get("previous_close", 0.0), context.get("today_open", 0.0))

        # Check 09:15 to 09:45 block
        if time_str < "09:15:00":
            self.market_phase = "WAITING"
            return

        if "09:15:00" <= time_str < "09:45:00":
            if self.market_phase != "IN POSITION":
                self.market_phase = "OPENING DISCOVERY"
            # No new entries
            return

        if self.market_phase in ["WAITING", "OPENING DISCOVERY"]:
            self.market_phase = "DISCOVERY COMPLETE"

        daily_atr = context.get('daily_atr', 0.0)
        day_high = context.get('day_high', 0.0)
        day_low = context.get('day_low', 0.0)

        atr_exhausted = False
        if daily_atr > 0 and (day_high - day_low) >= 0.95 * daily_atr:
            atr_exhausted = True

        if atr_exhausted and not self.active_position:
            self.market_phase = "EXHAUSTED"
            return

        # Entry Logic
        if not self.active_position and not atr_exhausted:
            trending_oi_percent = context.get('trending_oi_percent', 0.0)
            price = tick.get('price', 0.0)
            supertrend = context.get('supertrend', 0.0)
            vwap = context.get('vwap', 0.0)

            # Simplified trigger condition simulating a pullback & confirmation candle
            pullback_bullish = price > supertrend and price > vwap # simplified for testing
            pullback_bearish = price < supertrend and price < vwap # simplified for testing

            if trending_oi_percent >= 40 and pullback_bullish:
                if self.tier_1_status == "WAITING":
                    self.tier_1_status = "TRIGGERED"
                    self.active_position = True
                    self.market_phase = "IN POSITION"
                    await self.emit_signal(tick.get("instrument", ""), "BUY_CE", 0.8, "Bullish Trend Confirmation")
                elif self.tier_1_status == "TRIGGERED" and self.tier_2_status == "WAITING":
                    self.tier_2_status = "TRIGGERED"
                    await self.emit_signal(tick.get("instrument", ""), "BUY_CE", 0.8, "Bullish Tier 2 Confirmation")

            elif trending_oi_percent <= -40 and pullback_bearish:
                if self.tier_1_status == "WAITING":
                    self.tier_1_status = "TRIGGERED"
                    self.active_position = True
                    self.market_phase = "IN POSITION"
                    await self.emit_signal(tick.get("instrument", ""), "BUY_PE", 0.8, "Bearish Trend Confirmation")
                elif self.tier_1_status == "TRIGGERED" and self.tier_2_status == "WAITING":
                    self.tier_2_status = "TRIGGERED"
                    await self.emit_signal(tick.get("instrument", ""), "BUY_PE", 0.8, "Bearish Tier 2 Confirmation")

    async def emit_signal(self, instrument: str, direction: str, confidence: float, evidence: str):
        signal = {
            "signal_id": f"SIG_{self.strategy_id}_{datetime.now().timestamp()}",
            "strategy_id": self.strategy_id,
            "instrument": instrument,
            "timestamp": datetime.now().isoformat(),
            "direction": direction,
            "confidence": confidence,
            "evidence": evidence
        }
        await event_bus.publish("STRATEGY_SIGNAL", signal)
