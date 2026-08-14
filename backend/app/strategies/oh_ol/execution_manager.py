from enum import Enum, auto
from typing import Dict, Any, List

class TradeState(Enum):
    ENTRY_PENDING = auto()
    PARTIAL_FILL = auto()
    FULL_FILL = auto()
    TRAILING = auto()
    EXITED = auto()

class ExecutionManager:
    def __init__(self):
        self.state = TradeState.ENTRY_PENDING
        self.signals_emitted: List[Dict[str, Any]] = []
        self.entry_price_avg = 0.0
        self.stop_loss = 0.0
        self.tier1_filled = False
        self.tier2_filled = False
        self.instrument = ""
        self.direction = ""

    def initiate_entry(self, instrument: str, direction: str, supertrend_price: float, vwap_price: float):
        self.instrument = instrument
        self.direction = direction
        self.state = TradeState.ENTRY_PENDING

        # Tier 1: 2 Lots at SuperTrend
        self.signals_emitted.append({
            "type": "LIMIT_ORDER",
            "tier": 1,
            "instrument": instrument,
            "direction": direction,
            "lots": 2,
            "price": supertrend_price
        })

        # Tier 2: 4 Lots at VWAP
        self.signals_emitted.append({
            "type": "LIMIT_ORDER",
            "tier": 2,
            "instrument": instrument,
            "direction": direction,
            "lots": 4,
            "price": vwap_price
        })

        # Initial Stop Loss below VWAP (assuming long for now, for simplicity)
        # Assuming vwap_price is the lower entry point
        # A more robust system would calculate SL properly based on direction.
        # For simplicity, we just set a placeholder or an assumption.
        self.stop_loss = vwap_price * 0.995 if direction == "BUY" else vwap_price * 1.005

        return self.signals_emitted

    def update_fill(self, tier: int, fill_price: float):
        if tier == 1:
            self.tier1_filled = True
            # Update avg entry price
            if not self.tier2_filled:
                self.entry_price_avg = fill_price
                self.state = TradeState.PARTIAL_FILL
            else:
                self.entry_price_avg = (self.entry_price_avg * 4 + fill_price * 2) / 6
                self.state = TradeState.FULL_FILL
        elif tier == 2:
            self.tier2_filled = True
            if not self.tier1_filled:
                self.entry_price_avg = fill_price
                self.state = TradeState.PARTIAL_FILL
            else:
                self.entry_price_avg = (self.entry_price_avg * 2 + fill_price * 4) / 6
                self.state = TradeState.FULL_FILL

    def update_price(self, current_price: float, atr_exhausted: bool, target_hit: bool):
        if self.state in [TradeState.EXITED, TradeState.ENTRY_PENDING]:
            return None

        # Exit conditions
        exit_reason = None

        is_long = self.direction == "BUY"
        is_short = self.direction == "SELL"

        if (is_long and current_price <= self.stop_loss) or (is_short and current_price >= self.stop_loss):
            exit_reason = "STOP_LOSS_HIT"
        elif target_hit:
            exit_reason = "TARGET_HIT"
        elif atr_exhausted:
            exit_reason = "ATR_EXHAUSTION"

        if exit_reason:
            self.state = TradeState.EXITED
            return {"type": "FULL_EXIT", "reason": exit_reason}

        # Trailing State (Break-Even): If Tier 1 fills and price moves favored direction without filling Tier 2
        # Arbitrarily using a 0.5% move as "moved in favored direction" for this example
        if self.state == TradeState.PARTIAL_FILL and self.tier1_filled and not self.tier2_filled:
            moved_favored = (is_long and current_price > self.entry_price_avg * 1.005) or (is_short and current_price < self.entry_price_avg * 0.995)
            if moved_favored:
                self.state = TradeState.TRAILING
                self.stop_loss = self.entry_price_avg # Break-even
                return {"type": "PARTIAL_CLOSE", "lots": 1, "reason": "TRAILING_BREAK_EVEN"}

        return None
