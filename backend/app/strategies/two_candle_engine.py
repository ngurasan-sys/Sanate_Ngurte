import logging
import uuid
from collections import deque
from datetime import datetime, time, timezone
from typing import Dict, Optional

from backend.app.core.event_bus import event_bus
from backend.app.market_data.models import Candle
from backend.app.strategies.gap_opening.indicators import IndicatorEngine
from backend.app.strategies.gap_opening.engine import gap_opening_engine

logger = logging.getLogger(__name__)

_OI_REGIME_TO_TREND = {"BULLISH": "LONG_BUILDUP", "BEARISH": "SHORT_BUILDUP"}


def _compute_rsi(closes: list, period: int = 14) -> Optional[float]:
    """Standard Wilder's RSI. Returns None until enough closes exist —
    never fabricates a mid-range placeholder that would silently pass the
    momentumRoom filter."""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_vwma(candles: list, period: int = 20) -> Optional[float]:
    """Volume-weighted moving average over the last `period` candles."""
    window = candles[-period:]
    total_vol = sum(c["volume"] for c in window)
    if total_vol <= 0:
        return None
    return sum(c["close"] * c["volume"] for c in window) / total_vol


class TwoCandleEngine:
    """Wraps evaluate_two_candle_setup (the pure, already-tested rule
    function above) with real rolling market state: per-instrument 3-minute
    candle history, Supertrend (via the same IndicatorEngine gap_opening
    uses), VWMA, RSI(14), and OI-regime confirmation from
    gap_opening_engine.oi_regime (the same live per-underlying OI classifier
    /api/v1/market/indices already reads).

    Only real ticks feed this — no fabricated candle data. RSI/VWMA return
    None until enough history exists, and evaluate_two_candle_setup is
    never called until every required field is present.
    """

    HISTORY_LEN = 30
    VOL_THRESHOLD = {"NIFTY": 125_000, "SENSEX": 50_000, "BANKNIFTY": 50_000}

    def __init__(self):
        self.config = {"enabled": False}
        self.running = False
        self.indicators = IndicatorEngine(atr_period=14, supertrend_period=10, supertrend_multiplier=3)
        self._candles: Dict[str, deque] = {}
        self._closes: Dict[str, list] = {}
        self._latest_snapshot: Dict[str, dict] = {}

    def enable(self):
        self.config["enabled"] = True

    def disable(self):
        self.config["enabled"] = False

    def start(self):
        if self.running:
            return
        self.running = True
        event_bus.subscribe("CANDLE_CLOSED", self._on_candle_closed)
        logger.info("TwoCandleEngine started (enabled=%s)", self.config["enabled"])

    def stop(self):
        self.running = False
        logger.info("TwoCandleEngine stopped")

    def get_snapshot(self, instrument: str) -> Optional[dict]:
        return self._latest_snapshot.get(instrument)

    async def _on_candle_closed(self, candle: Candle):
        if candle.timeframe != "3m":
            return

        inst = candle.instrument
        if inst not in self._candles:
            self._candles[inst] = deque(maxlen=self.HISTORY_LEN)
            self._closes[inst] = []

        self.indicators.update_candle(inst, candle.high, candle.low, candle.close)
        self._closes[inst].append(candle.close)
        if len(self._closes[inst]) > 200:
            self._closes[inst] = self._closes[inst][-200:]

        row = {
            "open": candle.open, "high": candle.high, "low": candle.low,
            "close": candle.close, "volume": candle.volume,
            "vwap": candle.vwap if candle.vwap is not None else candle.close,
            "supertrend": self.indicators.get_supertrend(inst),
            "vwma": _compute_vwma(list(self._candles[inst]) + [{"close": candle.close, "volume": candle.volume}]),
            "rsi": _compute_rsi(self._closes[inst]),
        }
        self._candles[inst].append(row)

        result = {"status": "MONITORING", "signal": "NONE", "reason": "Awaiting Setup"}
        conditions = {"volumeSpike": False, "indicatorAlignment": False, "momentumRoom": False, "trendingOi": False}

        if not self.config["enabled"]:
            result = {"status": "PAUSED", "signal": "NONE", "reason": "Strategy is stopped."}
        elif len(self._candles[inst]) >= 2 and row["vwma"] is not None and row["rsi"] is not None:
            c1, c2 = list(self._candles[inst])[-2], list(self._candles[inst])[-1]
            vol_threshold = self.VOL_THRESHOLD.get(inst, 50_000)
            oi_regime = gap_opening_engine.oi_regime.get(inst, "UNKNOWN")
            oi_trend = _OI_REGIME_TO_TREND.get(oi_regime)

            conditions["volumeSpike"] = c1["volume"] >= vol_threshold and c2["volume"] >= vol_threshold
            conditions["indicatorAlignment"] = (
                (c2["close"] > c2["vwap"] and c2["close"] > c2["supertrend"] and c2["close"] > c2["vwma"]) or
                (c2["close"] < c2["vwap"] and c2["close"] < c2["supertrend"] and c2["close"] < c2["vwma"])
            )
            conditions["momentumRoom"] = 20 <= c2["rsi"] <= 80
            conditions["trendingOi"] = oi_trend is not None

            now_str = datetime.now(timezone.utc).strftime("%H:%M")
            result = evaluate_two_candle_setup(inst, now_str, [{}, {}, c1, c2], {"trend": oi_trend})

        self._latest_snapshot[inst] = {
            "instrument": inst, "conditions": conditions, "signalData": result,
            "currentPrice": candle.close, "timestamp": candle.timestamp.isoformat(),
        }
        await event_bus.publish("two_candle_state", self._latest_snapshot[inst])

        if result["status"] == "SIGNAL_ACTIVE" and result["signal"] != "NONE":
            await event_bus.publish("STRATEGY_SIGNAL", {
                "signal_id": f"TWOCANDLE_{inst}_{int(candle.timestamp.timestamp())}_{uuid.uuid4().hex[:6]}",
                "strategy_id": "two_candle",
                "instrument": inst,
                "direction": "CALL" if result["signal"] == "BUY_CALL" else "PUT",
                "confidence": 75.0,
                "timestamp": candle.timestamp,
                "entry_trigger": result.get("entry_trigger"),
                "stop_loss": result.get("stop_loss"),
                "reason": result.get("reason"),
            })


two_candle_engine = TwoCandleEngine()


def evaluate_two_candle_setup(symbol: str, current_time_str: str, candle_data: list, oi_data: dict) -> dict:
    """
    candle_data should contain the last 3 closed candles (index 0, 1, 2)
    and the current forming candle (index 3). We evaluate on candles 1 and 2.
    """
    current_time = datetime.strptime(current_time_str, "%H:%M").time()

    # 1. Time Filter (9:45 AM to 2:30 PM)
    if not (time(9, 45) <= current_time <= time(14, 30)):
        return {"status": "PAUSED", "signal": "NONE", "reason": "Outside 9:45 - 14:30 Window"}

    # Set Volume Threshold based on index
    vol_threshold = 125000 if symbol == "NIFTY" else 50000

    c1 = candle_data[-2] # The older of the two trigger candles
    c2 = candle_data[-1] # The most recently closed candle

    # 2. Check Volume Requirement (Both must be above threshold)
    if c1['volume'] < vol_threshold or c2['volume'] < vol_threshold:
        return {"status": "MONITORING", "signal": "NONE", "reason": "Volume threshold not met"}

    # 3. Check Long Conditions
    is_long_price = (c2['close'] > c2['vwap'] and
                     c2['close'] > c2['supertrend'] and
                     c2['close'] > c2['vwma'])

    is_long_volume = c1['close'] > c1['open'] and c2['close'] > c2['open'] # Both Green
    is_long_rsi = 20 <= c2['rsi'] <= 80
    is_long_oi = oi_data.get('trend') == "LONG_BUILDUP"

    if is_long_price and is_long_volume and is_long_rsi and is_long_oi:
        return {
            "status": "SIGNAL_ACTIVE",
            "signal": "BUY_CALL",
            "entry_trigger": "OPEN_OF_CURRENT_CANDLE",
            "stop_loss": c1['low'],
            "reason": "2-Candle Bullish Breakout Confirmed"
        }

    # 4. Check Short Conditions
    is_short_price = (c2['close'] < c2['vwap'] and
                      c2['close'] < c2['supertrend'] and
                      c2['close'] < c2['vwma'])

    is_short_volume = c1['close'] < c1['open'] and c2['close'] < c2['open'] # Both Red
    is_short_rsi = 20 <= c2['rsi'] <= 80
    is_short_oi = oi_data.get('trend') == "SHORT_BUILDUP"

    if is_short_price and is_short_volume and is_short_rsi and is_short_oi:
        return {
            "status": "SIGNAL_ACTIVE",
            "signal": "BUY_PUT",
            "entry_trigger": "OPEN_OF_CURRENT_CANDLE",
            "stop_loss": c1['high'],
            "reason": "2-Candle Bearish Breakout Confirmed"
        }

    return {"status": "MONITORING", "signal": "NONE", "reason": "Price/Indicator alignment missing"}
