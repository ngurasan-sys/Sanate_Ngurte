import asyncio
import logging
import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, WebSocket

from backend.app.api.live_stream_adapters import (
    adapt_oh_ol,
    adapt_trending_oi_price_action,
    sanitize_payload,
)
from backend.app.api.session_phase import compute_session_phase
from backend.app.strategies.gap_opening.engine import gap_opening_engine
from backend.app.strategies.oh_ol import oh_ol_strategy
from backend.app.strategies.trending_oi_price_action.engine import trending_oi_pa_engine

logger = logging.getLogger(__name__)

router = APIRouter()

SUPPORTED_STRATEGIES = {
    "trending_oi_price_action",
    "oh_ol",
    "straddle",
    "two_candle",
    "btst_cas",
    "pullback_chop",
}

_DEFAULT_INSTRUMENT = {
    "trending_oi_price_action": "NIFTY FUT",
    "oh_ol": "NIFTY",
}


def _build_payload(strategy: str, instrument: str) -> dict:
    now = datetime.now()
    session_phase = compute_session_phase(now.time())

    risk_status = []
    active_strategy_payload: dict = {}
    diff_oi_pct: Optional[float] = None
    atr_progress_pct: Optional[float] = None
    # gap_opening_engine.oi_regime is keyed by bare underlying ("NIFTY"),
    # not the " FUT"-suffixed instrument keys trending_oi_price_action
    # uses internally — normalize before lookup. Reports "UNKNOWN" only
    # when that underlying genuinely has no OI regime classification yet
    # (e.g. before the first trending_oi tick of the day), not as a
    # permanent placeholder.
    underlying = instrument.removesuffix(" FUT")
    regime = gap_opening_engine.oi_regime.get(underlying, "UNKNOWN")
    # diff_oi_pct is the same live, per-underlying dict as oi_regime, keyed
    # identically — so it is available for every strategy, not just
    # trending_oi_price_action.
    diff_oi_pct = gap_opening_engine.diff_oi_pct.get(underlying)

    if strategy == "trending_oi_price_action":
        state = trending_oi_pa_engine.positions.get(instrument)
        if state:
            risk_status, active_strategy_payload = adapt_trending_oi_price_action(state)
            if diff_oi_pct is None:
                diff_oi_pct = state.get("diff_oi_pct")

            daily_atr = state.get("daily_atr")
            atr_values = getattr(daily_atr, "atr_values", None)
            if atr_values:
                daily_atr_val = atr_values[-1]
                # current_day_high/low are reset only by 3m candles while
                # daily_atr is fed only by 1d candles, so a daily candle can
                # land first and leave high/low at their -inf/+inf defaults.
                # Guard on finiteness: uncomputable stays None, never 0.
                high = state.get("current_day_high", 0.0)
                low = state.get("current_day_low", 0.0)
                if daily_atr_val and math.isfinite(high) and math.isfinite(low):
                    atr_progress_pct = ((high - low) / daily_atr_val) * 100.0
        else:
            active_strategy_payload = {"status": "NO_ACTIVE_INSTRUMENT_STATE"}
    elif strategy == "oh_ol":
        risk_status, active_strategy_payload = adapt_oh_ol(oh_ol_strategy, instrument)

    payload = {
        "timestamp": now.isoformat(),
        "session_phase": session_phase,
        "risk_status": risk_status,
        "active_strategy_payload": active_strategy_payload,
        "market_stats": {
            "regime": regime,
            "oi_difference_pct": diff_oi_pct,
            "atr_progress_pct": atr_progress_pct,
        },
    }
    # _build_payload is the real JSON boundary: sanitize the assembled payload
    # once here so no individual computation site above has to remember to.
    return sanitize_payload(payload)


@router.websocket("/ws/live-stream")
async def live_stream(websocket: WebSocket, strategy: str = Query(...), instrument: Optional[str] = Query(None)):
    if strategy not in SUPPORTED_STRATEGIES:
        await websocket.close(code=1003, reason=f"Unknown strategy: {strategy}")
        return

    await websocket.accept()
    resolved_instrument = instrument or _DEFAULT_INSTRUMENT.get(strategy, "NIFTY")
    logger.info(f"live-stream client connected (strategy={strategy}, instrument={resolved_instrument})")

    try:
        while True:
            # ONLY payload construction is protected here. A send failure must
            # NOT be swallowed: WebSocketDisconnect and the ASGI server's own
            # transport-level disconnect exceptions are all Exception
            # subclasses, so catching around the send would keep the loop
            # (and its asyncio task) alive forever after the client is gone.
            try:
                payload = _build_payload(strategy, resolved_instrument)
            except Exception:
                logger.exception("Error building live-stream payload; continuing")
                await asyncio.sleep(1)
                continue

            await websocket.send_json(payload)
            await asyncio.sleep(1)
    except Exception:
        # Broad on purpose: the exception type raised on client disconnect
        # varies by ASGI server (starlette's WebSocketDisconnect, uvicorn's
        # ClientDisconnected, ...). Any send-path failure means the connection
        # is over — log it as a normal disconnect and end the task.
        logger.info(f"live-stream client disconnected (strategy={strategy})")
