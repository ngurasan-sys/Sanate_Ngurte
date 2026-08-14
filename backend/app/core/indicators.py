import math
from typing import List

class Supertrend:
    def __init__(self, period: int = 10, multiplier: float = 3.0):
        self.period = period
        self.multiplier = multiplier

        self.highs = []
        self.lows = []
        self.closes = []
        self.atrs = []
        self.supertrends = []
        self.directions = [] # 1 for bullish, -1 for bearish
        self.final_upper_bands = []
        self.final_lower_bands = []

    def _calculate_tr(self, high: float, low: float, prev_close: float) -> float:
        if prev_close is None:
            return high - low
        return max(high - low, abs(high - prev_close), abs(low - prev_close))

    def update(self, high: float, low: float, close: float) -> tuple:
        self.highs.append(high)
        self.lows.append(low)
        self.closes.append(close)

        prev_close = self.closes[-2] if len(self.closes) > 1 else None
        tr = self._calculate_tr(high, low, prev_close)

        if len(self.atrs) == 0:
            self.atrs.append(tr)
        elif len(self.atrs) < self.period:
            self.atrs.append((sum(self.atrs) + tr) / (len(self.atrs) + 1))
        else:
            self.atrs.append((self.atrs[-1] * (self.period - 1) + tr) / self.period)

        atr = self.atrs[-1]

        hl2 = (high + low) / 2.0
        basic_upper_band = hl2 + (self.multiplier * atr)
        basic_lower_band = hl2 - (self.multiplier * atr)

        if len(self.final_upper_bands) == 0:
            self.final_upper_bands.append(basic_upper_band)
            self.final_lower_bands.append(basic_lower_band)
            self.directions.append(1)
            self.supertrends.append(basic_lower_band)
            return self.supertrends[-1], self.directions[-1]

        prev_final_upper = self.final_upper_bands[-1]
        prev_final_lower = self.final_lower_bands[-1]
        prev_close_val = self.closes[-2]

        if basic_upper_band < prev_final_upper or prev_close_val > prev_final_upper:
            self.final_upper_bands.append(basic_upper_band)
        else:
            self.final_upper_bands.append(prev_final_upper)

        if basic_lower_band > prev_final_lower or prev_close_val < prev_final_lower:
            self.final_lower_bands.append(basic_lower_band)
        else:
            self.final_lower_bands.append(prev_final_lower)

        prev_dir = self.directions[-1]
        current_dir = prev_dir

        if prev_dir == 1 and close <= self.final_lower_bands[-1]:
            current_dir = -1
        elif prev_dir == -1 and close >= self.final_upper_bands[-1]:
            current_dir = 1

        self.directions.append(current_dir)

        if current_dir == 1:
            self.supertrends.append(self.final_lower_bands[-1])
        else:
            self.supertrends.append(self.final_upper_bands[-1])

        return self.supertrends[-1], self.directions[-1]
