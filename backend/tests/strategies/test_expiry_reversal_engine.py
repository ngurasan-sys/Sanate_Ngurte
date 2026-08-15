import pytest
from datetime import datetime, timedelta, timezone

from backend.app.strategies.expiry_reversal.engine import ExpiryReversalEngine
from backend.app.strategies.expiry_reversal.models import ExpiryReversalConfig
from backend.app.market_data.models import Candle, Tick


@pytest.fixture
def engine():
    config = ExpiryReversalConfig(
        oi_shift_window_minutes=3,
        call_oi_increase_threshold=1_000_000,
        put_oi_decrease_threshold=1_000_000,
        structural_break_min_candles=2,
        weak_candle_body_atr_ratio=0.3,
        tier_2_offset_points=10.0,
        tier_3_offset_points=25.0,
        stop_loss_buffer_points=5.0,
        partial_exit_pct=50.0,
    )
    e = ExpiryReversalEngine(config=config)
    return e


async def _seed_oi_history(engine, underlying, now, ce_before, pe_before, ce_now, pe_now):
    """Feed two trending_oi ticks 3+ minutes apart so the engine's rolling
    OI-shift window has both a 'before' and 'now' reading."""
    await engine._handle_trending_oi({
        "view": "spot_trending_oi",
        "underlying": underlying,
        "row": {"ceOi": ce_before, "peOi": pe_before},
    })
    engine._oi_history[underlying][-1] = (
        now - timedelta(minutes=engine.config.oi_shift_window_minutes, seconds=5),
        ce_before, pe_before,
    )
    await engine._handle_trending_oi({
        "view": "spot_trending_oi",
        "underlying": underlying,
        "row": {"ceOi": ce_now, "peOi": pe_now},
    })
    engine._oi_history[underlying][-1] = (now, ce_now, pe_now)


@pytest.mark.asyncio
async def test_futures_classification_tracked_from_trending_oi(engine):
    await engine._handle_trending_oi({
        "view": "future_trending_oi",
        "underlying": "NIFTY",
        "row": {"classification": "SHORT COVERING"},
    })
    assert engine.futures_classification["NIFTY"] == "SHORT_COVERING"


@pytest.mark.asyncio
async def test_weak_move_flag_set_on_small_candle_with_short_covering(engine):
    await engine._handle_trending_oi({
        "view": "future_trending_oi", "underlying": "NIFTY",
        "row": {"classification": "SHORT COVERING"},
    })

    dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(15):
        await engine._handle_candle_closed(Candle(
            instrument="NIFTY FUT", timeframe="1d", timestamp=dt,
            open=100, high=120, low=80, close=110, volume=1000,
        ))

    dt2 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    await engine._handle_candle_closed(Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=dt2,
        open=24000, high=24003, low=23999, close=24002, volume=100,
    ))

    state = engine._get_state("NIFTY FUT")
    assert state["weak_move_active"] is True


@pytest.mark.asyncio
async def test_bearish_structural_break_with_oi_shift_enters_tier_1(engine):
    dt2 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    dt3 = dt2 + timedelta(minutes=1)
    dt4 = dt3 + timedelta(minutes=3)

    # Anchor the OI history's "now" reading at dt4 — the timestamp of the
    # candle that will actually trigger the shift lookup.
    await _seed_oi_history(engine, "NIFTY", dt4, ce_before=13_000_000, pe_before=13_100_000,
                            ce_now=15_000_000, pe_now=7_800_000)

    state = engine._get_state("NIFTY FUT")
    state["current_day_str"] = "2026-01-01"
    state["current_day_high"] = 24200.0
    state["current_day_low"] = 24100.0

    await engine._handle_candle_closed(Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=dt3,
        open=24150, high=24155, low=24080, close=24090, volume=100,
    ))
    await engine._handle_candle_closed(Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=dt4,
        open=24090, high=24095, low=24050, close=24060, volume=100,
    ))

    assert state["position_state"] == "TIER_1_ENTERED"
    assert state["direction"] == "BEARISH"
    assert state["lots_held"] == engine.config.tier_1_lots
    # SL is placed off the triggering (confirming) candle's high — the
    # second candle, which is the one that actually confirms the break.
    assert state["current_sl"] == 24095.0 + engine.config.stop_loss_buffer_points


@pytest.mark.asyncio
async def test_no_entry_without_oi_shift_confirmation(engine):
    dt2 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    dt3 = dt2 + timedelta(minutes=1)
    dt4 = dt3 + timedelta(minutes=3)

    # OI barely moves — below threshold, should not confirm a shift.
    await _seed_oi_history(engine, "NIFTY", dt4, ce_before=13_000_000, pe_before=13_100_000,
                            ce_now=13_050_000, pe_now=13_080_000)

    state = engine._get_state("NIFTY FUT")
    state["current_day_str"] = "2026-01-01"
    state["current_day_high"] = 24200.0
    state["current_day_low"] = 24100.0

    await engine._handle_candle_closed(Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=dt3,
        open=24150, high=24155, low=24080, close=24090, volume=100,
    ))
    await engine._handle_candle_closed(Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=dt4,
        open=24090, high=24095, low=24050, close=24060, volume=100,
    ))

    assert state["position_state"] == "WAITING"


@pytest.mark.asyncio
async def test_late_expiry_session_atr_exhausted_skips_entry(engine):
    engine.config.is_expiry_day = True
    dt2 = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)
    dt3 = dt2 + timedelta(minutes=1)
    dt4 = dt3 + timedelta(minutes=3)

    await _seed_oi_history(engine, "NIFTY", dt4, ce_before=13_000_000, pe_before=13_100_000,
                            ce_now=15_000_000, pe_now=7_800_000)

    state = engine._get_state("NIFTY FUT")
    state["current_day_str"] = "2026-01-01"
    state["current_day_high"] = 24360.0
    state["current_day_low"] = 24100.0
    state["daily_atr"].atr_values = [270.0]

    await engine._handle_candle_closed(Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=dt3,
        open=24150, high=24155, low=24080, close=24090, volume=100,
    ))
    await engine._handle_candle_closed(Candle(
        instrument="NIFTY FUT", timeframe="3m", timestamp=dt4,
        open=24090, high=24095, low=24050, close=24060, volume=100,
    ))

    assert state["position_state"] == "WAITING"
    assert state["skipped_late_session"] is True


@pytest.mark.asyncio
async def test_partial_profit_books_half_and_moves_sl_to_breakeven(engine):
    state = engine._get_state("NIFTY FUT")
    state["position_state"] = "TIER_1_ENTERED"
    state["direction"] = "BEARISH"
    state["lots_held"] = 2
    state["avg_entry_price"] = 24090.0
    state["current_sl"] = 24160.0

    dt = datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc)
    await engine._handle_market_tick(Tick(instrument="NIFTY FUT", price=24070.0, timestamp=dt))

    assert state["partial_exit_done"] is True
    assert state["breakeven_done"] is True
    assert state["current_sl"] == 24090.0
    assert state["lots_held"] == 1
    assert state["position_state"] == "PARTIAL_EXIT"


@pytest.mark.asyncio
async def test_stop_loss_hit_exits_all(engine):
    state = engine._get_state("NIFTY FUT")
    state["position_state"] = "TIER_1_ENTERED"
    state["direction"] = "BEARISH"
    state["lots_held"] = 2
    state["avg_entry_price"] = 24090.0
    state["current_sl"] = 24160.0

    dt = datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc)
    await engine._handle_market_tick(Tick(instrument="NIFTY FUT", price=24165.0, timestamp=dt))

    assert state["position_state"] == "EXITED"
    assert state["lots_held"] == 0


@pytest.mark.asyncio
async def test_get_state_snapshot_no_active_instrument():
    engine = ExpiryReversalEngine()
    snapshot = engine.get_state_snapshot("NIFTY FUT")
    assert snapshot == {"status": "NO_ACTIVE_INSTRUMENT_STATE"}


@pytest.mark.asyncio
async def test_get_state_snapshot_reflects_real_state(engine):
    state = engine._get_state("NIFTY FUT")
    state["position_state"] = "TIER_1_ENTERED"
    state["direction"] = "BEARISH"
    state["lots_held"] = 2

    snapshot = engine.get_state_snapshot("NIFTY FUT")
    assert snapshot["position_state"] == "TIER_1_ENTERED"
    assert snapshot["direction"] == "BEARISH"
    assert snapshot["lots_held"] == 2
