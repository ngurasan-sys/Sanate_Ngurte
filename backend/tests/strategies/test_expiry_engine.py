from unittest.mock import AsyncMock, patch

import pytest

from backend.app.core import active_broker as ab_module
from backend.app.strategies import expiry_engine as engine_module
from backend.app.strategies.expiry_engine import (
    ExpiryOITrackerEngine,
    build_macro_clue,
    build_strike_payload,
    classify_strike_sentiment,
    find_atm_strike,
    select_atm_window,
)
from backend.app.market_data.option_chain_client import OptionChainLookupError


class _FakeAuth:
    def __init__(self, token):
        self._token = token

    def load_token(self):
        return self._token


class _FakeProvider:
    def __init__(self, fetch_mock):
        self.fetch_option_chain = fetch_mock

    def instrument_key_for_index(self, underlying):
        return "NSE_INDEX|Nifty 50"


def _activate(monkeypatch, token, fetch_mock=None):
    registry = ab_module.ActiveBrokerRegistry()
    registry.register_broker(
        "upstox", provider=_FakeProvider(fetch_mock or AsyncMock()), auth_module=_FakeAuth(token),
    )
    registry._active_broker_id = "upstox"
    monkeypatch.setattr(engine_module, "active_broker", registry)
    return registry


def _make_row(strike: float, spot: float, call_oi=100000, call_prev_oi=100000,
              put_oi=100000, put_prev_oi=100000, call_ltp=50.0, call_close=50.0,
              put_ltp=50.0, put_close=50.0):
    return {
        "strike_price": strike,
        "underlying_spot_price": spot,
        "call_options": {"market_data": {
            "ltp": call_ltp, "close_price": call_close, "oi": call_oi, "prev_oi": call_prev_oi,
        }},
        "put_options": {"market_data": {
            "ltp": put_ltp, "close_price": put_close, "oi": put_oi, "prev_oi": put_prev_oi,
        }},
    }


def test_classify_strike_sentiment_long_buildup():
    assert classify_strike_sentiment(ltp=110, close_price=100, oi=200, prev_oi=150) == "LONG_BUILDUP"


def test_classify_strike_sentiment_short_covering():
    assert classify_strike_sentiment(ltp=110, close_price=100, oi=100, prev_oi=150) == "SHORT_COVERING"


def test_find_atm_strike_picks_nearest():
    chain = [_make_row(s, 24510) for s in [24400, 24450, 24500, 24550, 24600]]
    assert find_atm_strike(chain, 24510) == 24500


def test_select_atm_window_five_above_five_below():
    strikes = [24000 + i * 50 for i in range(20)]  # 24000..24950
    chain = [_make_row(s, 24500) for s in strikes]
    windowed = select_atm_window(chain, spot_price=24500, window=5)

    assert len(windowed) == 11  # atm + 5 above + 5 below
    assert windowed[0]["strike_price"] == 24250
    assert windowed[-1]["strike_price"] == 24750
    assert any(row["strike_price"] == 24500 for row in windowed)


def test_select_atm_window_truncates_at_chain_edges():
    strikes = [24000, 24050, 24100]
    chain = [_make_row(s, 24000) for s in strikes]
    windowed = select_atm_window(chain, spot_price=24000, window=5)
    assert len(windowed) == 3


def test_select_atm_window_empty_chain_returns_empty():
    assert select_atm_window([], spot_price=24000, window=5) == []


def test_build_strike_payload_shape_and_atm_flag():
    # Call: price up (120 > 100) + OI down (700000 < 800000) => SHORT_COVERING.
    # Put: price down (90 < 100) + OI down (600000 < 750000) => LONG_UNWINDING.
    row = _make_row(24500, 24510, call_oi=700000, call_prev_oi=800000,
                     call_ltp=120, call_close=100, put_oi=600000, put_prev_oi=750000,
                     put_ltp=90, put_close=100)
    payload = build_strike_payload(row, atm_strike=24500)

    assert payload["strike_price"] == 24500
    assert payload["is_atm"] is True
    assert payload["call_data"] == {"ltp": 120, "oi_total": 700000, "sentiment": "SHORT_COVERING"}
    assert payload["put_data"] == {"ltp": 90, "oi_total": 600000, "sentiment": "LONG_UNWINDING"}


def test_build_strike_payload_not_atm():
    row = _make_row(24600, 24510)
    payload = build_strike_payload(row, atm_strike=24500)
    assert payload["is_atm"] is False


def test_build_macro_clue_detects_deep_itm_call_short_covering():
    spot = 24500
    # Deep ITM calls (well below spot) all showing a big OI drop.
    chain = [
        _make_row(24000, spot, call_oi=700000, call_prev_oi=1_000_000),
        _make_row(24050, spot, call_oi=750000, call_prev_oi=1_000_000),
        _make_row(24100, spot, call_oi=800000, call_prev_oi=1_000_000),
        _make_row(24500, spot, call_oi=100000, call_prev_oi=100000),
    ]
    clue = build_macro_clue(chain, spot, deep_itm_count=3, drop_threshold_pct=15.0)
    assert clue is not None
    assert "Short Covering" in clue


def test_build_macro_clue_none_when_no_significant_drop():
    spot = 24500
    chain = [
        _make_row(24000, spot, call_oi=990000, call_prev_oi=1_000_000),
        _make_row(24500, spot, call_oi=100000, call_prev_oi=100000),
    ]
    clue = build_macro_clue(chain, spot, deep_itm_count=3, drop_threshold_pct=15.0)
    assert clue is None


def test_build_macro_clue_none_when_no_itm_strikes():
    spot = 24000
    chain = [_make_row(24500, spot)]  # only OTM strikes, nothing below spot
    assert build_macro_clue(chain, spot) is None


@pytest.mark.asyncio
async def test_poll_loop_publishes_insufficient_data_without_token(monkeypatch):
    engine = ExpiryOITrackerEngine()
    published = []

    async def capture(topic, payload):
        published.append(payload)
        engine.running = False  # stop after first publish

    _activate(monkeypatch, token=None)
    with patch(
        "backend.app.strategies.expiry_engine.event_bus.publish", new=capture,
    ):
        engine.running = True
        await engine._poll_loop()

    assert published[0]["sufficient_data"] is False
    assert "token" in published[0]["reason"].lower()


@pytest.mark.asyncio
async def test_poll_loop_falls_back_to_next_week_when_current_week_empty(monkeypatch):
    engine = ExpiryOITrackerEngine()
    chain = [_make_row(24500, 24510)]
    published = []

    async def capture(topic, payload):
        published.append(payload)
        engine.running = False

    fetch_mock = AsyncMock(side_effect=[OptionChainLookupError("empty"), chain])

    _activate(monkeypatch, token="tok", fetch_mock=fetch_mock)
    with patch(
        "backend.app.strategies.expiry_engine.event_bus.publish", new=capture,
    ):
        engine.running = True
        await engine._poll_loop()

    assert fetch_mock.await_count == 2
    assert fetch_mock.await_args_list[0].args[2] == "current_week"
    assert fetch_mock.await_args_list[1].args[2] == "next_week"
    assert published[0]["sufficient_data"] is True
    assert published[0]["spot_price"] == 24510


@pytest.mark.asyncio
async def test_poll_loop_publishes_insufficient_data_on_total_lookup_failure(monkeypatch):
    engine = ExpiryOITrackerEngine()
    published = []

    async def capture(topic, payload):
        published.append(payload)
        engine.running = False

    fetch_mock = AsyncMock(side_effect=OptionChainLookupError("boom"))

    _activate(monkeypatch, token="tok", fetch_mock=fetch_mock)
    with patch(
        "backend.app.strategies.expiry_engine.event_bus.publish", new=capture,
    ):
        engine.running = True
        await engine._poll_loop()

    assert published[0]["sufficient_data"] is False
    assert "boom" in published[0]["reason"]
