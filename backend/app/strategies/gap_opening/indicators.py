from typing import Dict, List, Optional
from datetime import datetime

class IndicatorEngine:
    def __init__(self, atr_period: int = 14, supertrend_period: int = 10, supertrend_multiplier: int = 3):
        self.atr_period = atr_period
        self.st_period = supertrend_period
        self.st_multiplier = supertrend_multiplier

        self.history: Dict[str, List[dict]] = {}
        self.atr: Dict[str, float] = {}
        self.supertrend: Dict[str, float] = {}
        self.supertrend_direction: Dict[str, int] = {}  # 1 for bullish, -1 for bearish

    def update_candle(self, instrument: str, high: float, low: float, close: float, prev_close: Optional[float] = None):
        if instrument not in self.history:
            self.history[instrument] = []

        pc = prev_close
        if pc is None and self.history[instrument]:
            pc = self.history[instrument][-1]["close"]
        elif pc is None:
            pc = close

        tr = max(high - low, abs(high - pc), abs(low - pc))
        prev_atr = self.atr.get(instrument)

        if prev_atr is None:
             self.history[instrument].append({"high": high, "low": low, "close": close, "tr": tr})
             if len(self.history[instrument]) >= self.atr_period:
                 avg_tr = sum(c["tr"] for c in self.history[instrument][-self.atr_period:]) / self.atr_period
                 self.atr[instrument] = avg_tr
             else:
                 self.atr[instrument] = tr
        else:
             new_atr = (prev_atr * (self.atr_period - 1) + tr) / self.atr_period
             self.atr[instrument] = new_atr
             self.history[instrument].append({"high": high, "low": low, "close": close, "tr": tr})

        if len(self.history[instrument]) > 50:
             self.history[instrument].pop(0)

        curr_atr = self.atr[instrument]
        hl2 = (high + low) / 2

        basic_upperband = hl2 + (self.st_multiplier * curr_atr)
        basic_lowerband = hl2 - (self.st_multiplier * curr_atr)

        if instrument not in self.supertrend:
            self.supertrend_direction[instrument] = 1
            self.supertrend[instrument] = basic_lowerband
            self.history[instrument][-1]["final_ub"] = basic_upperband
            self.history[instrument][-1]["final_lb"] = basic_lowerband
            return

        prev_hist = self.history[instrument][-2] if len(self.history[instrument]) > 1 else None
        prev_final_ub = prev_hist.get("final_ub", basic_upperband) if prev_hist else basic_upperband
        prev_final_lb = prev_hist.get("final_lb", basic_lowerband) if prev_hist else basic_lowerband
        prev_dir = self.supertrend_direction.get(instrument, 1)
        prev_close_st = pc

        if basic_upperband < prev_final_ub or prev_close_st > prev_final_ub:
            final_ub = basic_upperband
        else:
            final_ub = prev_final_ub

        if basic_lowerband > prev_final_lb or prev_close_st < prev_final_lb:
            final_lb = basic_lowerband
        else:
            final_lb = prev_final_lb

        if prev_dir == 1 and close < final_lb:
            curr_dir = -1
        elif prev_dir == -1 and close > final_ub:
            curr_dir = 1
        else:
            curr_dir = prev_dir

        self.supertrend_direction[instrument] = curr_dir

        if curr_dir == 1:
            self.supertrend[instrument] = final_lb
        else:
            self.supertrend[instrument] = final_ub

        self.history[instrument][-1]["final_ub"] = final_ub
        self.history[instrument][-1]["final_lb"] = final_lb

    def get_atr(self, instrument: str) -> float:
        return self.atr.get(instrument, 0.0)

    def get_supertrend(self, instrument: str) -> float:
        return self.supertrend.get(instrument, 0.0)
