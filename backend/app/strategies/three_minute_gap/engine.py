"""3-Minute Gap — Fair Value Gap (FVG) discovery on 3-minute candles.

An FVG is the classic 3-candle imbalance pattern: candle[0].high <
candle[2].low leaves an unfilled "gap" zone (bullish FVG) between them, or
candle[0].low > candle[2].high (bearish FVG). Price often returns to fill
that zone before continuing in the gap's direction — this engine watches
for that pullback, confirmed by SuperTrend direction and trending-OI
regime, before emitting a signal.

Same real-data constraint as every other strategy here: no futures Level-2
feed is wired in yet (see order_flow/mock_feed.py's module docstring), so
this runs on the same NIFTY/SENSEX/BANKNIFTY spot 3-minute candles
gap_opening_engine and two_candle_engine already consume — not fabricated
"NIFTY FUT" candles that don't exist anywhere in this codebase.
"""

import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, Optional

from backend.app.core.event_bus import event_bus
from backend.app.market_data.models import Candle
from backend.app.strategies.gap_opening.engine import gap_opening_engine
from backend.app.strategies.gap_opening.indicators import IndicatorEngine

logger = logging.getLogger(__name__)

OI_CONFIRMATION_THRESHOLD_PCT = 40.0  # matches the frontend's existing >=40% confirmation threshold


class ThreeCandleGap:
    __slots__ = ("gap_type", "base", "top", "status", "formed_at")

    def __init__(self, gap_type: str, base: float, top: float, formed_at: datetime):
        self.gap_type = gap_type  # "BULLISH" | "BEARISH"
        self.base = base
        self.top = top
        self.status = "OPEN"  # OPEN | FILLED | INVALIDATED
        self.formed_at = formed_at


def detect_fvg(c0: dict, c2: dict) -> Optional[Dict]:
    """3-candle FVG check using candle[0] and candle[2] (candle[1] is the
    displacement candle in between, unused in the classic definition)."""
    if c0["high"] < c2["low"]:
        return {"gap_type": "BULLISH", "base": c0["high"], "top": c2["low"]}
    if c0["low"] > c2["high"]:
        return {"gap_type": "BEARISH", "base": c2["high"], "top": c0["low"]}
    return None


class ThreeMinuteGapEngine:
    HISTORY_LEN = 30

    def __init__(self):
        self.config = {"enabled": False}
        self.running = False
        self.indicators = IndicatorEngine(atr_period=14, supertrend_period=10, supertrend_multiplier=3)
        self._candles: Dict[str, Deque[dict]] = {}
        self._active_gap: Dict[str, Optional[ThreeCandleGap]] = {}
        self._day_high: Dict[str, float] = {}
        self._day_low: Dict[str, float] = {}
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
        logger.info("ThreeMinuteGapEngine started (enabled=%s)", self.config["enabled"])

    def stop(self):
        self.running = False
        logger.info("ThreeMinuteGapEngine stopped")

    def get_snapshot(self, instrument: str) -> Optional[dict]:
        return self._latest_snapshot.get(instrument)

    async def _on_candle_closed(self, candle: Candle):
        if candle.timeframe != "3m":
            return

        inst = candle.instrument
        if inst not in self._candles:
            self._candles[inst] = deque(maxlen=self.HISTORY_LEN)
            self._active_gap[inst] = None

        self.indicators.update_candle(inst, candle.high, candle.low, candle.close)
        row = {"open": candle.open, "high": candle.high, "low": candle.low,
               "close": candle.close, "volume": candle.volume,
               "vwap": candle.vwap if candle.vwap is not None else candle.close,
               "timestamp": candle.timestamp}
        self._candles[inst].append(row)

        self._day_high[inst] = max(self._day_high.get(inst, candle.high), candle.high)
        self._day_low[inst] = min(self._day_low.get(inst, candle.low), candle.low)

        supertrend = self.indicators.get_supertrend(inst)
        trend_dir = self.indicators.supertrend_direction.get(inst, 0)
        three_min_trend = "BULLISH" if trend_dir == 1 else "BEARISH" if trend_dir == -1 else "--"

        candles = list(self._candles[inst])
        # New FVG check: needs at least 3 candles, no gap already active.
        if self._active_gap[inst] is None and len(candles) >= 3:
            detected = detect_fvg(candles[-3], candles[-1])
            if detected:
                self._active_gap[inst] = ThreeCandleGap(
                    detected["gap_type"], detected["base"], detected["top"], candle.timestamp,
                )
                logger.info("%s: new %s FVG detected [%.2f, %.2f]", inst,
                            detected["gap_type"], detected["base"], detected["top"])

        gap = self._active_gap[inst]
        pullback_status = "--"
        supertrend_interaction = "--"
        fvg_interaction = "--"
        entry_status = "NO_SETUP"
        signal_action = "WAIT"
        signal_reason = "No active FVG."
        result_signal: Optional[dict] = None

        if gap is not None:
            in_zone = gap.base <= candle.close <= gap.top
            if gap.status == "OPEN" and in_zone:
                gap.status = "FILLED"
            elif gap.status == "OPEN" and (
                (gap.gap_type == "BULLISH" and candle.close < gap.base) or
                (gap.gap_type == "BEARISH" and candle.close > gap.top)
            ):
                gap.status = "INVALIDATED"

            fvg_interaction = "IN_ZONE" if in_zone else ("ABOVE" if candle.close > gap.top else "BELOW")
            pullback_status = "PULLBACK_IN_PROGRESS" if gap.status == "FILLED" else gap.status
            supertrend_interaction = "ALIGNED" if (
                (gap.gap_type == "BULLISH" and trend_dir == 1) or
                (gap.gap_type == "BEARISH" and trend_dir == -1)
            ) else "MISALIGNED"

            oi_regime = gap_opening_engine.oi_regime.get(inst, "UNKNOWN")
            diff_oi_pct = gap_opening_engine.diff_oi_pct.get(inst)
            oi_confirms = (
                diff_oi_pct is not None and abs(diff_oi_pct) >= OI_CONFIRMATION_THRESHOLD_PCT and
                ((gap.gap_type == "BULLISH" and oi_regime == "BULLISH") or
                 (gap.gap_type == "BEARISH" and oi_regime == "BEARISH"))
            )

            if not self.config["enabled"]:
                entry_status = "STOPPED"
                signal_reason = "Strategy is stopped."
            elif gap.status == "FILLED" and supertrend_interaction == "ALIGNED" and oi_confirms:
                entry_status = "ENTRY_CONFIRMED"
                signal_action = "BUY_CALL" if gap.gap_type == "BULLISH" else "BUY_PUT"
                signal_reason = f"FVG filled, SuperTrend {three_min_trend.lower()}, OI confirms."
                stop_loss = gap.base if gap.gap_type == "BULLISH" else gap.top
                result_signal = {
                    "signal": signal_action, "stop_loss": stop_loss,
                    "reason": signal_reason, "gap_type": gap.gap_type,
                }
                # Gap has produced its one entry — retire it so we don't
                # keep re-signaling on this same imbalance every candle.
                self._active_gap[inst] = None
            elif gap.status == "INVALIDATED":
                entry_status = "INVALIDATED"
                signal_reason = "Gap invalidated — price closed through the zone."
                self._active_gap[inst] = None
            else:
                entry_status = "WAITING_FOR_CONFLUENCE"
                signal_reason = "Awaiting SuperTrend/OI confluence."

        diff_oi_pct_val = gap_opening_engine.diff_oi_pct.get(inst) or 0.0
        oi_regime_val = gap_opening_engine.oi_regime.get(inst, "UNKNOWN")

        snapshot = {
            "instrument": inst,
            "isConnected": True,
            "strategyStatus": "RUNNING" if self.config["enabled"] else "STOPPED",
            "underlying": inst,
            "executionMode": "ALGO" if self.config["enabled"] else "DATA_ONLY",
            "futuresPrice": candle.close,
            "threeMinTrend": three_min_trend,
            "superTrend": supertrend,
            "vwap": row["vwap"],
            "dayHigh": self._day_high[inst],
            "dayLow": self._day_low[inst],
            "gapType": gap.gap_type if gap else "--",
            "gapBase": gap.base if gap else 0.0,
            "gapTop": gap.top if gap else 0.0,
            "gapStatus": gap.status if gap else "NO_GAP",
            "diffOi": 0,
            "diffOiPercent": diff_oi_pct_val,
            "strengthDots": min(5, int(abs(diff_oi_pct_val) / 20)),
            "sentiment": oi_regime_val,
            "pullbackStatus": pullback_status,
            "superTrendInteraction": supertrend_interaction,
            "fvgInteraction": fvg_interaction,
            "entryStatus": entry_status,
            "signalAction": signal_action,
            "signalReason": signal_reason,
            "signalTime": candle.timestamp.strftime("%H:%M:%S"),
        }
        self._latest_snapshot[inst] = snapshot
        await event_bus.publish("three_minute_gap_state", snapshot)

        if result_signal:
            await event_bus.publish("STRATEGY_SIGNAL", {
                "signal_id": f"3MGAP_{inst}_{int(candle.timestamp.timestamp())}_{uuid.uuid4().hex[:6]}",
                "strategy_id": "three_minute_gap",
                "instrument": inst,
                "direction": "CALL" if result_signal["signal"] == "BUY_CALL" else "PUT",
                "confidence": 78.0,
                "timestamp": candle.timestamp,
                "stop_loss": result_signal["stop_loss"],
                "reason": result_signal["reason"],
            })


three_minute_gap_engine = ThreeMinuteGapEngine()
