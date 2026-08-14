import math
from typing import List, Dict, Any, Optional

class SuperTrendIndicator:
    def __init__(self, period: int = 10, multiplier: float = 2.0):
        self.period = period
        self.multiplier = multiplier

        self.highs = []
        self.lows = []
        self.closes = []

        self.basic_ub = []
        self.basic_lb = []
        self.final_ub = []
        self.final_lb = []

        self.supertrend = []
        self.trend = []  # 1 for bullish, -1 for bearish
        self.atr_values = []

    def add_candle(self, high: float, low: float, close: float) -> Optional[Dict[str, Any]]:
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)

        if len(self.closes) < 2:
            self.atr_values.append(high - low)
            self.basic_ub.append(0.0)
            self.basic_lb.append(0.0)
            self.final_ub.append(0.0)
            self.final_lb.append(0.0)
            self.supertrend.append(0.0)
            self.trend.append(1)
            return None

        # Calculate True Range
        tr = max(
            high - low,
            abs(high - self.closes[-2]),
            abs(low - self.closes[-2])
        )

        # Calculate ATR
        if len(self.atr_values) < self.period:
            self.atr_values.append((sum(self.atr_values) + tr) / (len(self.atr_values) + 1))
        else:
            prev_atr = self.atr_values[-1]
            current_atr = ((prev_atr * (self.period - 1)) + tr) / self.period
            self.atr_values.append(current_atr)

        current_atr = self.atr_values[-1]

        hl2 = (high + low) / 2.0
        bub = hl2 + (self.multiplier * current_atr)
        blb = hl2 - (self.multiplier * current_atr)

        self.basic_ub.append(bub)
        self.basic_lb.append(blb)

        # Final Upper Band
        if len(self.final_ub) < 2:
            self.final_ub.append(bub)
        else:
            prev_fub = self.final_ub[-1]
            if bub < prev_fub or self.closes[-2] > prev_fub:
                self.final_ub.append(bub)
            else:
                self.final_ub.append(prev_fub)

        # Final Lower Band
        if len(self.final_lb) < 2:
            self.final_lb.append(blb)
        else:
            prev_flb = self.final_lb[-1]
            if blb > prev_flb or self.closes[-2] < prev_flb:
                self.final_lb.append(blb)
            else:
                self.final_lb.append(prev_flb)

        # Supertrend
        if len(self.supertrend) < 2:
            self.supertrend.append(0.0)
            self.trend.append(1)
        else:
            prev_st = self.supertrend[-1]
            prev_trend = self.trend[-1]

            if prev_st == self.final_ub[-2]:
                if close > self.final_ub[-1]:
                    self.trend.append(1)
                    self.supertrend.append(self.final_lb[-1])
                else:
                    self.trend.append(-1)
                    self.supertrend.append(self.final_ub[-1])
            elif prev_st == self.final_lb[-2]:
                if close < self.final_lb[-1]:
                    self.trend.append(-1)
                    self.supertrend.append(self.final_ub[-1])
                else:
                    self.trend.append(1)
                    self.supertrend.append(self.final_lb[-1])
            else:
                # Should not happen if history is continuous
                self.trend.append(1)
                self.supertrend.append(self.final_lb[-1])

        if len(self.closes) >= self.period:
            return {
                "supertrend": self.supertrend[-1],
                "trend": self.trend[-1],
                "atr": self.atr_values[-1]
            }
        return None

class DailyATR:
    def __init__(self, period: int = 14):
        self.period = period
        self.highs = []
        self.lows = []
        self.closes = []
        self.atr_values = []
        self.current_day = None

        self.current_day_high = -math.inf
        self.current_day_low = math.inf

    def add_daily_candle(self, high: float, low: float, close: float) -> Optional[float]:
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)

        if len(self.closes) < 2:
            self.atr_values.append(high - low)
            return None

        tr = max(
            high - low,
            abs(high - self.closes[-2]),
            abs(low - self.closes[-2])
        )

        if len(self.atr_values) < self.period:
            self.atr_values.append((sum(self.atr_values) + tr) / (len(self.atr_values) + 1))
        else:
            prev_atr = self.atr_values[-1]
            current_atr = ((prev_atr * (self.period - 1)) + tr) / self.period
            self.atr_values.append(current_atr)

        if len(self.closes) >= self.period:
            return self.atr_values[-1]
        return None
