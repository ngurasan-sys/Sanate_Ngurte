import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.api.endpoints.live_stream import _build_payload, live_stream
from backend.app.main import app
from backend.app.strategies.gap_opening.engine import gap_opening_engine
from backend.app.strategies.trending_oi_price_action.engine import trending_oi_pa_engine


class _FakeDailyAtr:
    def __init__(self, values):
        self.atr_values = values


class _FakeWebSocket:
    """Minimal WebSocket double: records sends and can fail on the Nth one."""

    def __init__(self, fail_on_send_number=None, error=RuntimeError("client gone")):
        self.fail_on_send_number = fail_on_send_number
        self.error = error
        self.send_count = 0
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000, reason=""):
        pass

    async def send_json(self, payload):
        self.send_count += 1
        if self.fail_on_send_number is not None and self.send_count >= self.fail_on_send_number:
            raise self.error


def test_live_stream_rejects_unknown_strategy():
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/live-stream?strategy=not_a_real_strategy"):
                pass


def test_live_stream_missing_strategy_param_rejected():
    with TestClient(app) as client:
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/live-stream"):
                pass


def test_live_stream_accepts_supported_strategy_and_sends_payload():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live-stream?strategy=trending_oi_price_action") as ws:
            payload = ws.receive_json()

            assert "timestamp" in payload
            assert payload["session_phase"] in {
                "CLOSED", "CONTINUOUS", "DECAY", "CAS", "GOLDEN_WINDOW",
            }
            assert isinstance(payload["risk_status"], list)
            assert isinstance(payload["active_strategy_payload"], dict)
            assert set(payload["market_stats"].keys()) == {
                "regime", "oi_difference_pct", "atr_progress_pct",
            }
            # Standing guard: the frame must be strictly valid JSON. Starlette
            # sends with allow_nan=True, so a non-finite float would ship as a
            # bare Infinity/NaN literal that a browser's JSON.parse rejects.
            json.dumps(payload, allow_nan=False)


def test_live_stream_oh_ol_strategy_payload_shape():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live-stream?strategy=oh_ol") as ws:
            payload = ws.receive_json()

            assert "timestamp" in payload
            assert isinstance(payload["risk_status"], list)
            assert isinstance(payload["active_strategy_payload"], dict)
            assert set(payload["market_stats"].keys()) == {
                "regime", "oi_difference_pct", "atr_progress_pct",
            }
            json.dumps(payload, allow_nan=False)


def test_live_stream_oi_difference_pct_populated_for_non_trending_strategy():
    # straddle resolves to the bare "NIFTY" instrument; diff_oi_pct must be
    # read from the same per-underlying gap-engine dict that feeds `regime`.
    #
    # gap_opening_engine.handle_trending_oi is patched to a no-op for the
    # duration of this test: it's a real subscriber to the "trending_oi"
    # event-bus topic, and trending_oi_engine's own 1Hz publish loop fires
    # unconditionally (even with all-default-zero data when no real OI
    # ticks have arrived yet) as soon as it's been running for ~1s. In the
    # full real app — which this test intentionally exercises via
    # TestClient(app) to verify the live-stream endpoint's actual wiring —
    # that loop can genuinely fire within this test's window and overwrite
    # the value under test with a fabricated 0.0 before the assertion runs,
    # which has nothing to do with what this test verifies (the endpoint
    # correctly reads gap_opening_engine.diff_oi_pct for non-trending
    # strategies). Patching this one handler removes that unrelated race
    # without disabling anything the assertion itself depends on.
    had_key = "NIFTY" in gap_opening_engine.diff_oi_pct
    previous = gap_opening_engine.diff_oi_pct.get("NIFTY")
    gap_opening_engine.diff_oi_pct["NIFTY"] = 42.5
    try:
        with patch.object(
            gap_opening_engine, "handle_trending_oi", new=AsyncMock()
        ):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/live-stream?strategy=straddle") as ws:
                    payload = ws.receive_json()
                    assert payload["market_stats"]["oi_difference_pct"] == 42.5
    finally:
        if had_key:
            gap_opening_engine.diff_oi_pct["NIFTY"] = previous
        else:
            gap_opening_engine.diff_oi_pct.pop("NIFTY", None)


def test_atr_progress_pct_is_none_when_day_high_low_still_infinite():
    # Reproduction of the real race: a 1d candle populates daily_atr while no
    # 3m candle has landed yet, so current_day_high/low are still at their
    # -inf/+inf sentinels. atr_progress_pct must stay None (never 0, never
    # -Infinity), and the whole payload must survive strict JSON.
    instrument = "NIFTY FUT"
    had_state = instrument in trending_oi_pa_engine.positions
    previous = trending_oi_pa_engine.positions.get(instrument)
    trending_oi_pa_engine.positions[instrument] = {
        "position_state": "WAITING",
        "current_day_high": -float("inf"),
        "current_day_low": float("inf"),
        "time_filter_status": "VALID",
        "distance_filter_status": "VALID",
        "rejection_reason": "",
        "diff_oi_pct": 0.0,
        "daily_atr": _FakeDailyAtr([120.0]),
    }
    try:
        payload = _build_payload("trending_oi_price_action", instrument)

        assert payload["market_stats"]["atr_progress_pct"] is None
        json.dumps(payload, allow_nan=False)
    finally:
        if had_state:
            trending_oi_pa_engine.positions[instrument] = previous
        else:
            trending_oi_pa_engine.positions.pop(instrument, None)


def test_atr_progress_pct_computed_when_day_range_is_finite():
    instrument = "NIFTY FUT"
    had_state = instrument in trending_oi_pa_engine.positions
    previous = trending_oi_pa_engine.positions.get(instrument)
    trending_oi_pa_engine.positions[instrument] = {
        "position_state": "WAITING",
        "current_day_high": 24060.0,
        "current_day_low": 24000.0,
        "time_filter_status": "VALID",
        "distance_filter_status": "VALID",
        "rejection_reason": "",
        "diff_oi_pct": 0.0,
        "daily_atr": _FakeDailyAtr([120.0]),
    }
    try:
        payload = _build_payload("trending_oi_price_action", instrument)
        assert payload["market_stats"]["atr_progress_pct"] == pytest.approx(50.0)
    finally:
        if had_state:
            trending_oi_pa_engine.positions[instrument] = previous
        else:
            trending_oi_pa_engine.positions.pop(instrument, None)


def test_live_stream_loop_exits_when_send_fails():
    # A send failure (client disconnect, whatever exception type the ASGI
    # server raises) must end the handler coroutine, not be swallowed by the
    # payload-construction handler and looped on forever.
    ws = _FakeWebSocket(fail_on_send_number=1)

    async def _run():
        await asyncio.wait_for(
            live_stream(ws, strategy="straddle", instrument="NIFTY"),
            timeout=5,
        )

    asyncio.run(_run())

    assert ws.accepted is True
    assert ws.send_count == 1


def test_live_stream_loop_survives_payload_construction_error(monkeypatch):
    # The inverse guarantee: a payload-construction error is logged and the
    # loop continues (it does not exit), so the coroutine never returns.
    monkeypatch.setattr(
        "backend.app.api.endpoints.live_stream._build_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")),
    )
    ws = _FakeWebSocket()

    async def _run():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                live_stream(ws, strategy="straddle", instrument="NIFTY"),
                timeout=0.2,
            )

    asyncio.run(_run())

    assert ws.send_count == 0


def test_live_stream_strategy_without_adapter_reports_empty_risk_status():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/live-stream?strategy=straddle") as ws:
            payload = ws.receive_json()
            assert payload["risk_status"] == []
