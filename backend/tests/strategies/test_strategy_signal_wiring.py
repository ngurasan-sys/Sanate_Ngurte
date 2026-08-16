"""Regression tests for the buy-side strategy wiring fixes:

- Trending OI + Price Action called an undefined self._get_strike() —
  AttributeError on every real BUY_CE/BUY_PE entry. Fixed by reusing
  StrikeSelectionService (gap_opening's existing resolver).
- ATR Strategies and Gap Opening Strategies emitted STRATEGY_SIGNAL
  without an `instrument` or `confidence` field — OpportunityEngine
  silently drops any signal missing those (see opportunity.py), so
  neither ever produced a real Opportunity/trade.
- Intraday Trend Scalper never emitted STRATEGY_SIGNAL at all — pure
  telemetry, no path to risk/execution.
- Expiry Reversal only ever published to its own expiry_reversal_signal
  channel (websocket/frontend display only) and never resolved an actual
  option strike — never reached STRATEGY_SIGNAL/OpportunityEngine either.
  Fixed additively: expiry_reversal_signal is unchanged (the frontend
  still reads BULLISH/BEARISH from it), a new STRATEGY_SIGNAL is published
  alongside it for genuine trade actions only (not the bookkeeping-only
  SKIP_LATE_SESSION/CANCEL_PENDING_TIERS actions).

Each strategy is exercised directly (not through the full live tick/candle
pipeline — that's covered by each strategy's own test file) and its
emitted signal is fed straight into OpportunityEngine.process_signal to
prove it actually converts, rather than just checking the dict shape.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.engines.opportunity import OpportunityEngine
from backend.app.market_data.models import Candle, Tick
from backend.app.strategies.atr.atr_strategies_engine import ATRStrategiesEngine
from backend.app.strategies.expiry_reversal.engine import ExpiryReversalEngine
from backend.app.strategies.gap_opening.engine import GapOpeningEngine
from backend.app.strategies.gap_opening.models import PositionState
from backend.app.strategies.intraday_trend_scalper.engine import IntradayTrendScalper
from backend.app.strategies.trending_oi_price_action.engine import TrendingOIPriceActionStrategy


async def _capture_signal(coro_that_publishes) -> dict:
    """Runs a coroutine that calls event_bus.publish("STRATEGY_SIGNAL", ...)
    and returns the published signal dict, without needing a running
    EventBus worker loop.
    """
    captured = {}

    async def _fake_publish(channel, payload):
        if channel == "STRATEGY_SIGNAL":
            captured["signal"] = payload

    with patch("backend.app.core.event_bus.event_bus.publish", side_effect=_fake_publish):
        await coro_that_publishes()

    assert "signal" in captured, "no STRATEGY_SIGNAL was published"
    return captured["signal"]


async def _assert_converts_to_opportunity(signal: dict):
    """The real proof of "wired into risk/execution": feed the signal
    through the actual OpportunityEngine and confirm it produces an
    Opportunity rather than being logged-and-dropped.
    """
    engine = OpportunityEngine()
    await engine.process_signal(signal if isinstance(signal, dict) else signal)
    assert len(engine.opportunities) == 1
    return engine.opportunities[0]


# --------------------------- Trending OI + Price Action ---------------------------

@pytest.mark.asyncio
async def test_trending_oi_price_action_execute_signal_no_longer_crashes():
    engine = TrendingOIPriceActionStrategy()
    state = engine._get_instrument_state("NIFTY FUT")
    state["bullish_oi_confirmed"] = True
    state["diff_oi_pct"] = 50.0

    candle = Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=datetime(2024, 10, 1, 10, 0, tzinfo=timezone.utc),
        open=24480, high=24520, low=24470, close=24500, volume=100,
    )

    signal = await _capture_signal(lambda: engine._execute_signal(candle, state, "BUY_CE", True, 24490.0, "Bullish Pullback Confirmed"))

    assert signal["instrument"] == "NIFTY24500CE"  # candle.close=24500 -> nearest 50-strike is itself
    assert signal["action"] == "BUY_CE"
    assert signal["confidence"] > 0


@pytest.mark.asyncio
async def test_trending_oi_price_action_signal_converts_to_opportunity():
    engine = TrendingOIPriceActionStrategy()
    state = engine._get_instrument_state("NIFTY FUT")
    state["bullish_oi_confirmed"] = True

    candle = Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=datetime(2024, 10, 1, 10, 0, tzinfo=timezone.utc),
        open=24480, high=24520, low=24470, close=24500, volume=100,
    )
    signal = await _capture_signal(lambda: engine._execute_signal(candle, state, "BUY_CE", True, 24490.0, "Bullish Pullback Confirmed"))
    await _assert_converts_to_opportunity(signal)


# --------------------------- ATR Strategies ---------------------------

@pytest.mark.asyncio
async def test_atr_signal_has_instrument_and_confidence():
    engine = ATRStrategiesEngine()
    candle = Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=datetime(2024, 10, 1, 10, 0, tzinfo=timezone.utc),
        open=24480, high=24520, low=24470, close=24500, volume=100,
    )

    signal = await _capture_signal(lambda: engine._enter_tier_1("NIFTY", "BUY_CE", candle, "Bullish confluence"))

    assert signal["instrument"] == "NIFTY24500CE"
    assert signal["confidence"] == 80.0
    assert signal["strike_price"] == 24500
    assert signal["option_type"] == "CE"


@pytest.mark.asyncio
async def test_atr_signal_converts_to_opportunity():
    engine = ATRStrategiesEngine()
    candle = Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=datetime(2024, 10, 1, 10, 0, tzinfo=timezone.utc),
        open=24480, high=24520, low=24470, close=24500, volume=100,
    )
    signal = await _capture_signal(lambda: engine._enter_tier_1("NIFTY", "BUY_PE", candle, "Bearish confluence"))
    opp = await _assert_converts_to_opportunity(signal)
    assert opp.direction == "PUT"


# --------------------------- Gap Opening Strategies ---------------------------

@pytest.mark.asyncio
async def test_gap_opening_signal_has_instrument_and_confidence():
    engine = GapOpeningEngine()
    engine.state["NIFTY"] = PositionState()
    dt = datetime(2024, 10, 1, 9, 46, tzinfo=timezone.utc)

    signal = await _capture_signal(lambda: engine._execute_entry("NIFTY", 24500.0, dt, "BULLISH", "STANDARD", 24490.0, 24480.0))

    assert signal["instrument"]  # resolved from state.selected_strike/option_type, not blank
    assert "CE" in signal["instrument"] or "PE" in signal["instrument"]
    assert signal["confidence"] == 80.0


@pytest.mark.asyncio
async def test_gap_opening_signal_converts_to_opportunity():
    engine = GapOpeningEngine()
    engine.state["NIFTY"] = PositionState()
    dt = datetime(2024, 10, 1, 9, 46, tzinfo=timezone.utc)
    signal = await _capture_signal(lambda: engine._execute_entry("NIFTY", 24500.0, dt, "BEARISH", "STANDARD", 24490.0, 24480.0))
    await _assert_converts_to_opportunity(signal)


# --------------------------- Intraday Trend Scalper ---------------------------

@pytest.mark.asyncio
async def test_intraday_trend_scalper_tier_1_entry_emits_signal():
    engine = IntradayTrendScalper()
    state = engine._get_instrument_state("NIFTY FUT")
    state["position_direction"] = 1  # CE
    state["current_day_low"] = 24400.0

    signal = await _capture_signal(lambda: engine._execute_entry("NIFTY FUT", state, "ENTRY_TIER_1", 2, 24500.0, 24390.0))

    assert signal["action"] == "BUY_CE"
    assert signal["direction"] == "CALL"
    assert signal["instrument"] == "NIFTY24500CE"
    assert signal["confidence"] == 80.0
    assert signal["lots"] == 2


@pytest.mark.asyncio
async def test_intraday_trend_scalper_signal_converts_to_opportunity():
    engine = IntradayTrendScalper()
    state = engine._get_instrument_state("NIFTY FUT")
    state["position_direction"] = -1  # PE

    signal = await _capture_signal(lambda: engine._execute_entry("NIFTY FUT", state, "ENTRY_TIER_1", 2, 24500.0, 24610.0))
    opp = await _assert_converts_to_opportunity(signal)
    assert opp.direction == "PUT"


@pytest.mark.asyncio
async def test_intraday_trend_scalper_stop_loss_hit_emits_exit_signal():
    engine = IntradayTrendScalper()
    state = engine._get_instrument_state("NIFTY FUT")
    state["state"] = "ENTRY_TIER_1"
    state["position_direction"] = 1
    state["avg_entry_price"] = 24500.0
    state["current_sl"] = 24450.0
    state["lots_held"] = 2

    tick = Tick(instrument="NIFTY FUT", price=24440.0, timestamp=datetime(2024, 10, 1, 10, 5, tzinfo=timezone.utc))
    signal = await _capture_signal(lambda: engine._handle_market_tick(tick))

    assert signal["action"] == "EXIT_ALL"
    assert state["state"] == "EXITED"


# --------------------------- Expiry Reversal ---------------------------

async def _capture_both_channels(coro_that_publishes) -> dict:
    """Like _capture_signal, but also captures expiry_reversal_signal so
    a test can assert that channel is unchanged by the STRATEGY_SIGNAL
    addition.
    """
    captured = {}

    async def _fake_publish(channel, payload):
        captured[channel] = payload

    with patch("backend.app.core.event_bus.event_bus.publish", side_effect=_fake_publish):
        await coro_that_publishes()

    return captured


@pytest.mark.asyncio
async def test_expiry_reversal_tier_1_entry_publishes_both_channels():
    engine = ExpiryReversalEngine()
    state = engine._get_state("NIFTY FUT")

    candle = Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=datetime(2024, 10, 30, 14, 45, tzinfo=timezone.utc),
        open=24480, high=24520, low=24470, close=24500, volume=100,
    )

    captured = await _capture_both_channels(lambda: engine._enter_tier_1(candle, state, "BULLISH"))

    # Old channel: untouched, still BULLISH/BEARISH, still reaches only the frontend.
    old_signal = captured["expiry_reversal_signal"]
    assert old_signal["direction"] == "BULLISH"
    assert old_signal["action"] == "ENTER_TIER_1"

    # New channel: resolves an actual CE strike and uses the CALL/PUT convention.
    new_signal = captured["STRATEGY_SIGNAL"]
    assert new_signal["direction"] == "CALL"
    assert "CE" in new_signal["instrument"]
    assert new_signal["confidence"] == 80.0


@pytest.mark.asyncio
async def test_expiry_reversal_bearish_tier_1_signal_converts_to_opportunity():
    engine = ExpiryReversalEngine()
    state = engine._get_state("NIFTY FUT")

    candle = Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=datetime(2024, 10, 30, 14, 45, tzinfo=timezone.utc),
        open=24520, high=24530, low=24470, close=24500, volume=100,
    )

    captured = await _capture_both_channels(lambda: engine._enter_tier_1(candle, state, "BEARISH"))
    new_signal = captured["STRATEGY_SIGNAL"]
    assert new_signal["direction"] == "PUT"
    assert "PE" in new_signal["instrument"]

    opp = await _assert_converts_to_opportunity(new_signal)
    assert opp.direction == "PUT"


@pytest.mark.asyncio
async def test_expiry_reversal_stop_loss_hit_publishes_strategy_signal():
    engine = ExpiryReversalEngine()
    state = engine._get_state("NIFTY FUT")
    state["position_state"] = "TIER_1_ENTERED"
    state["direction"] = "BULLISH"
    state["avg_entry_price"] = 24500.0
    state["current_sl"] = 24450.0
    state["lots_held"] = 2

    tick = Tick(instrument="NIFTY FUT", price=24440.0, timestamp=datetime(2024, 10, 30, 14, 50, tzinfo=timezone.utc))
    captured = await _capture_both_channels(lambda: engine._check_stop_loss(tick, state))

    assert captured["expiry_reversal_signal"]["action"] == "EXIT_ALL"
    assert captured["STRATEGY_SIGNAL"]["action"] == "EXIT_ALL"
    assert captured["STRATEGY_SIGNAL"]["direction"] == "CALL"


@pytest.mark.asyncio
async def test_expiry_reversal_skip_late_session_does_not_publish_strategy_signal():
    """SKIP_LATE_SESSION is bookkeeping ("we decided NOT to trade"), not a
    real trade action — it must never reach STRATEGY_SIGNAL, or
    OpportunityEngine would fabricate a real Opportunity out of a skip.
    """
    engine = ExpiryReversalEngine()

    captured = await _capture_both_channels(
        lambda: engine._emit_signal("NIFTY FUT", "SKIP_LATE_SESSION", "BULLISH", 0, None, "Range exhausted"),
    )

    assert "expiry_reversal_signal" in captured
    assert "STRATEGY_SIGNAL" not in captured
