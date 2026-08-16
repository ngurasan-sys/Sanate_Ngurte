from datetime import datetime, timezone

import pytest

from backend.app.market_data.models import Tick
from backend.app.strategies.straddle.straddle_engine import (
    StraddleEngine,
    StraddleTracker,
    check_straddle_regime,
)


# --------------------------- check_straddle_regime ---------------------------

def test_regime_balanced_oi_is_non_directional_sell():
    # 5% difference — well inside the 20% "balanced" band
    assert check_straddle_regime(call_oi=105_000, put_oi=100_000) == "NON_DIRECTIONAL_STRADDLE_SELL"


def test_regime_large_oi_skew_is_directional_trending():
    # 50% difference — past the 45% directional threshold
    assert check_straddle_regime(call_oi=200_000, put_oi=100_000) == "DIRECTIONAL_TRENDING"


def test_regime_mid_skew_is_no_trade_zone():
    # 30% difference — between the two thresholds
    assert check_straddle_regime(call_oi=130_000, put_oi=100_000) == "NO_TRADE_ZONE"


def test_regime_zero_oi_is_uncertain():
    assert check_straddle_regime(call_oi=0, put_oi=0) == "UNCERTAIN"


# --------------------------- StraddleTracker ---------------------------

def test_tracker_vwap_is_volume_weighted_average():
    tracker = StraddleTracker(atm_strike=24500)
    ts = datetime(2024, 1, 1, 9, 20, tzinfo=timezone.utc)

    tracker.process_tick({"ltp": 100.0, "volume": 10.0}, {"ltp": 50.0, "volume": 10.0}, ts)
    tracker.process_tick({"ltp": 200.0, "volume": 30.0}, {"ltp": 100.0, "volume": 30.0}, ts)

    # combined premiums: 150 @ vol 20, 300 @ vol 60 -> vwap = (150*20 + 300*60)/(20+60)
    expected_vwap = (150.0 * 20.0 + 300.0 * 60.0) / (20.0 + 60.0)
    assert tracker.calculate_vwap() == pytest.approx(expected_vwap)


def test_tracker_ema_seeds_from_first_price_then_smooths():
    tracker = StraddleTracker(atm_strike=24500)
    first = tracker.calculate_ema(100.0, period=20)
    assert first == pytest.approx(100.0)

    second = tracker.calculate_ema(200.0, period=20)
    multiplier = 2 / 21
    assert second == pytest.approx((200.0 - 100.0) * multiplier + 100.0)


def test_tracker_signal_hold_short_while_premium_below_vwap():
    tracker = StraddleTracker(atm_strike=24500)
    ts = datetime(2024, 1, 1, 9, 20, tzinfo=timezone.utc)

    # First tick: vwap is computed *after* folding in this tick's own
    # volume, so premium always equals vwap exactly on tick one — and
    # equality fails the strict "< vwap" check, giving EXIT_ABOVE_VWAP.
    out = tracker.process_tick({"ltp": 100.0, "volume": 100.0}, {"ltp": 50.0, "volume": 100.0}, ts)
    assert out["combined_premium"] == 150.0
    assert out["signal"] == "EXIT_ABOVE_VWAP"

    # Second tick: premium (80) drops below the now-established running
    # vwap (115) -> hold the short.
    out2 = tracker.process_tick({"ltp": 50.0, "volume": 100.0}, {"ltp": 30.0, "volume": 100.0}, ts)
    assert out2["combined_premium"] == 80.0
    assert out2["vwap"] == pytest.approx(115.0)
    assert out2["signal"] == "HOLD_SHORT"


# --------------------------- StraddleEngine ---------------------------

def _tick(instrument: str, price: float, volume: float = 0.0) -> Tick:
    return Tick(instrument=instrument, price=price, volume=volume, timestamp=datetime(2024, 1, 1, 9, 20, tzinfo=timezone.utc))


def test_get_atm_strike_rounds_to_nearest_50():
    engine = StraddleEngine()
    assert engine._get_atm_strike(24523) == 24500
    assert engine._get_atm_strike(24538) == 24550


@pytest.mark.asyncio
async def test_engine_tracks_spot_and_builds_straddle_state_from_ce_pe_ticks():
    engine = StraddleEngine(underlying_symbol="NIFTY")

    await engine._handle_market_tick(_tick("NIFTY", 24500.0))
    await engine._handle_market_tick(_tick("NIFTY24500CE", 120.0, volume=100))
    await engine._handle_market_tick(_tick("NIFTY24500PE", 110.0, volume=100))

    assert engine.tracker is not None
    assert engine.tracker.atm_strike == 24500
    assert engine.current_state["atm_strike"] == 24500
    assert engine.current_state["straddle_data"]["current_premium"] == pytest.approx(230.0)


@pytest.mark.asyncio
async def test_engine_switches_tracker_when_atm_strike_moves():
    engine = StraddleEngine(underlying_symbol="NIFTY")

    await engine._handle_market_tick(_tick("NIFTY", 24500.0))
    await engine._handle_market_tick(_tick("NIFTY24500CE", 120.0, volume=100))
    await engine._handle_market_tick(_tick("NIFTY24500PE", 110.0, volume=100))
    first_tracker = engine.tracker

    # Spot moves enough to shift the rounded ATM strike
    await engine._handle_market_tick(_tick("NIFTY", 24560.0))
    assert engine.tracker is not first_tracker
    assert engine.tracker.atm_strike == 24550


@pytest.mark.asyncio
async def test_engine_never_sees_oi_because_tick_model_has_no_oi_field():
    """Tick (backend/app/market_data/models.py) has no `oi` field, so
    `hasattr(tick, "oi")` in _handle_market_tick is always False — call/put
    OI stay at their 0.0 default forever, and check_straddle_regime always
    falls through to "UNCERTAIN". This documents the current (likely
    unintended) behavior rather than silently leaving it uncovered.
    """
    engine = StraddleEngine(underlying_symbol="NIFTY")

    await engine._handle_market_tick(_tick("NIFTY", 24500.0))
    await engine._handle_market_tick(_tick("NIFTY24500CE", 120.0, volume=100))
    await engine._handle_market_tick(_tick("NIFTY24500PE", 110.0, volume=100))

    assert engine.ce_state[24500.0]["oi"] == 0.0
    assert engine.pe_state[24500.0]["oi"] == 0.0
    assert engine.current_state["market_regime"] == "UNCERTAIN"
