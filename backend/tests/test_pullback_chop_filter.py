import pytest
import asyncio
from datetime import datetime, timezone
from backend.app.strategies.pullback_chop_filter.engine import PullbackChopFilterStrategy
from backend.app.market_data.models import Tick, Candle

@pytest.fixture
def strategy():
    return PullbackChopFilterStrategy()

@pytest.mark.asyncio
async def test_chop_zone_bands(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)

    # Init Supertrend and VWAP to mock bands
    state["last_vwap"] = 100.0
    state["current_st"] = 110.0

    # Tick inside bands, should trigger CHOP_ZONE
    await strategy._evaluate_state(instrument, state, 105.0)
    assert state["market_state"] == "CHOP_ZONE"
    assert state["internal_state"] == "WAITING"
    assert state["active_signal"]["type"] == "WAIT"

@pytest.mark.asyncio
async def test_chop_zone_oi_conviction(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)

    state["last_vwap"] = 100.0
    state["current_st"] = 90.0
    # Price outside band
    ltp = 105.0

    # Low Conviction
    state["oi_diff_pct"] = 35.0
    await strategy._evaluate_state(instrument, state, ltp)
    assert state["market_state"] == "CHOP_ZONE"

@pytest.mark.asyncio
async def test_bullish_trend_confirmation_and_tiers(strategy):
    """SuperTrend(100) is the shallower band, VWAP(90) the deeper one —
    the "normal" configuration where SuperTrend tracks closer to price.
    """
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)

    state["last_vwap"] = 90.0
    state["current_st"] = 100.0
    state["oi_diff_pct"] = 45.0

    # 1. Breakout -> Trend confirmed
    await strategy._evaluate_state(instrument, state, 105.0)
    assert state["market_state"] == "TRENDING_BULLISH"
    assert state["internal_state"] == "BULLISH_TREND_CONFIRMED"

    # 2. Pullback to SuperTrend (Tier 1, the shallower/upper band)
    await strategy._evaluate_state(instrument, state, 100.0)
    assert state["internal_state"] == "BULLISH_TIER_1"
    assert state["active_signal"]["type"] == "BUY_TIER_1"
    assert "SuperTrend" in state["active_signal"]["message"]

    # 3. Continued pullback to VWAP (Tier 2, the deeper/lower band)
    await strategy._evaluate_state(instrument, state, 90.0)
    assert state["internal_state"] == "BULLISH_TIER_2"
    assert state["active_signal"]["type"] == "BUY_TIER_2"
    assert "VWAP" in state["active_signal"]["message"]

@pytest.mark.asyncio
async def test_bearish_trend_and_invalidation(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)

    state["last_vwap"] = 100.0
    state["current_st"] = 110.0
    state["oi_diff_pct"] = -50.0

    # 1. Breakdown -> Trend confirmed
    await strategy._evaluate_state(instrument, state, 90.0)
    assert state["market_state"] == "TRENDING_BEARISH"
    assert state["internal_state"] == "BEARISH_TREND_CONFIRMED"

    # 2. Invalidate on candle close
    candle = Candle(
        instrument=instrument,
        timeframe="3m",
        timestamp=datetime.now(timezone.utc),
        open=95.0,
        high=102.0,
        low=90.0,
        close=101.0, # Closes above VWAP (100.0)
        volume=100,
        is_closed=True
    )
    await strategy._check_invalidation(candle, state)
    assert state["market_state"] == "CHOP_ZONE"
    assert state["internal_state"] == "INVALIDATED"
    assert state["active_signal"]["type"] == "STOP_LOSS_HIT"


# --------------------------- Band calculation ---------------------------

@pytest.mark.asyncio
async def test_upper_and_lower_band_are_max_min_of_vwap_and_supertrend(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)
    state["last_vwap"] = 105.0
    state["current_st"] = 95.0
    state["oi_diff_pct"] = 0.0  # irrelevant to band math itself

    await strategy._evaluate_state(instrument, state, 100.0)
    assert state["upper_band"] == 105.0
    assert state["lower_band"] == 95.0


# --------------------------- Bearish pullback tiers ---------------------------

@pytest.mark.asyncio
async def test_bearish_trend_confirmation_and_tiers(strategy):
    """SuperTrend(100) is the shallower band here (mirrors the bullish
    test) — lower_band for a bearish setup, touched first on the way up.
    """
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)

    state["last_vwap"] = 110.0
    state["current_st"] = 100.0
    state["oi_diff_pct"] = -50.0

    # 1. Breakdown -> Trend confirmed
    await strategy._evaluate_state(instrument, state, 90.0)
    assert state["market_state"] == "TRENDING_BEARISH"
    assert state["internal_state"] == "BEARISH_TREND_CONFIRMED"

    # 2. Pullback to SuperTrend (Tier 1, the shallower/lower band)
    await strategy._evaluate_state(instrument, state, 100.0)
    assert state["internal_state"] == "BEARISH_TIER_1"
    assert state["active_signal"]["type"] == "BUY_TIER_1"
    assert "SuperTrend" in state["active_signal"]["message"]

    # 3. Continued pullback to VWAP (Tier 2, the deeper/upper band)
    await strategy._evaluate_state(instrument, state, 110.0)
    assert state["internal_state"] == "BEARISH_TIER_2"
    assert state["active_signal"]["type"] == "BUY_TIER_2"
    assert "VWAP" in state["active_signal"]["message"]


# --------------------------- Tier ordering ---------------------------

@pytest.mark.asyncio
async def test_tier_2_cannot_fire_before_tier_1(strategy):
    """Even if price crashes straight through the SuperTrend level in a
    single tick (past where Tier 2's VWAP level sits too), the state
    machine must still land on Tier 1 first — the BULLISH_TREND_CONFIRMED
    branch only ever checks the SuperTrend touch; Tier 2's VWAP check is
    only reachable from the BULLISH_TIER_1 state, one tick later.
    """
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)
    state["last_vwap"] = 100.0
    state["current_st"] = 90.0
    state["oi_diff_pct"] = 45.0

    await strategy._evaluate_state(instrument, state, 105.0)
    assert state["internal_state"] == "BULLISH_TREND_CONFIRMED"

    # Price crashes straight through SuperTrend (and past VWAP) in one tick.
    await strategy._evaluate_state(instrument, state, 85.0)
    assert state["internal_state"] == "BULLISH_TIER_1"  # not BULLISH_TIER_2
    assert state["active_signal"]["type"] == "BUY_TIER_1"


# --------------------------- No spurious re-transitions ---------------------------

@pytest.mark.asyncio
async def test_tier_2_does_not_fire_on_repeated_tier_1_price_when_vwap_is_the_shallower_band(strategy):
    """Regression test for a real defect found while writing this
    coverage: Tier 2 used to be a hardcoded "ltp <= last_vwap" check,
    which only behaved correctly if VWAP sat BELOW SuperTrend in a
    bullish trend. Here last_vwap(100) is *above* current_st(90) — the
    upper_band, not the lower one — so the old code let Tier 2 fire on
    the very next tick after Tier 1, at the *same* price, with zero
    further retracement.

    Fixed by keying Tier 1/Tier 2 off upper_band/lower_band directly
    (whichever indicator that turns out to be) instead of hardcoding
    "Tier 1 = SuperTrend, Tier 2 = VWAP" — see the engine's _band_label
    and the comments on the BULLISH_TIER_1 branch.
    """
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)
    state["last_vwap"] = 100.0   # upper_band here
    state["current_st"] = 90.0   # lower_band here
    state["oi_diff_pct"] = 45.0

    await strategy._evaluate_state(instrument, state, 105.0)  # trend confirmed
    await strategy._evaluate_state(instrument, state, 100.0)  # tier 1: touches upper_band (VWAP, in this fixture)
    assert state["internal_state"] == "BULLISH_TIER_1"
    assert "VWAP" in state["active_signal"]["message"]

    # Same price repeated — no further retracement at all. Must NOT
    # advance to Tier 2 (that requires reaching lower_band = 90).
    await strategy._evaluate_state(instrument, state, 100.0)
    assert state["internal_state"] == "BULLISH_TIER_1"

    # Genuine further retracement to the deeper band (SuperTrend, in this
    # fixture) now correctly fires Tier 2.
    await strategy._evaluate_state(instrument, state, 90.0)
    assert state["internal_state"] == "BULLISH_TIER_2"
    assert "SuperTrend" in state["active_signal"]["message"]


# --------------------------- Tick vs candle-close invalidation ---------------------------

@pytest.mark.asyncio
async def test_ltp_below_vwap_without_candle_close_does_not_trigger_stop(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)
    state["last_vwap"] = 100.0
    state["current_st"] = 90.0
    state["oi_diff_pct"] = 45.0
    state["internal_state"] = "BULLISH_TIER_1"
    state["market_state"] = "TRENDING_BULLISH"

    # A tick below VWAP — _evaluate_state (tick-driven) must not invalidate;
    # only _check_invalidation (candle-close-driven) may do that.
    await strategy._evaluate_state(instrument, state, 95.0)
    assert state["internal_state"] != "INVALIDATED"


@pytest.mark.asyncio
async def test_candle_close_above_vwap_invalidates_bearish_setup(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)
    state["last_vwap"] = 100.0
    state["internal_state"] = "BEARISH_TIER_1"

    candle = Candle(
        instrument=instrument, timeframe="3m", timestamp=datetime.now(timezone.utc),
        open=98.0, high=103.0, low=97.0, close=102.0, volume=100, is_closed=True,
    )
    await strategy._check_invalidation(candle, state)
    assert state["internal_state"] == "INVALIDATED"
    assert state["active_signal"]["message"] == "Candle closed above VWAP. Thesis invalidated."


# --------------------------- Missing/degraded data ---------------------------

@pytest.mark.asyncio
async def test_missing_vwap_or_supertrend_produces_wait_not_a_crash(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)
    state["last_vwap"] = None
    state["current_st"] = 95.0

    await strategy._evaluate_state(instrument, state, 100.0)
    assert state["active_signal"]["type"] == "WAIT"
    assert "Waiting for VWAP and SuperTrend" in state["active_signal"]["message"]


@pytest.mark.asyncio
async def test_zero_oi_diff_pct_is_chop_not_a_crash(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)
    state["last_vwap"] = 100.0
    state["current_st"] = 90.0
    state["oi_diff_pct"] = 0.0

    await strategy._evaluate_state(instrument, state, 105.0)
    assert state["market_state"] == "CHOP_ZONE"


@pytest.mark.asyncio
async def test_missing_oi_history_defaults_to_zero_and_stays_chop(strategy):
    """A freshly-created instrument state (no trending_oi tick ever
    received) has oi_diff_pct at its 0.0 default — must read as chop, not
    crash or accidentally read as a directional conviction.
    """
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)
    assert state["oi_diff_pct"] == 0.0

    state["last_vwap"] = 100.0
    state["current_st"] = 90.0
    await strategy._evaluate_state(instrument, state, 105.0)
    assert state["market_state"] == "CHOP_ZONE"


# --------------------------- Trend reversal / conviction loss ---------------------------

@pytest.mark.asyncio
async def test_oi_conviction_disappearing_mid_trend_returns_to_chop(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)
    state["last_vwap"] = 100.0
    state["current_st"] = 90.0
    state["oi_diff_pct"] = 45.0

    await strategy._evaluate_state(instrument, state, 105.0)
    await strategy._evaluate_state(instrument, state, 90.0)
    assert state["internal_state"] == "BULLISH_TIER_1"

    # OI conviction fades below threshold mid-setup.
    state["oi_diff_pct"] = 20.0
    await strategy._evaluate_state(instrument, state, 90.0)
    assert state["market_state"] == "CHOP_ZONE"
    assert state["internal_state"] == "WAITING"


@pytest.mark.asyncio
async def test_trend_reversal_from_bullish_to_bearish(strategy):
    instrument = "NIFTY FUT"
    state = strategy._get_instrument_state(instrument)
    state["last_vwap"] = 100.0
    state["current_st"] = 90.0
    state["oi_diff_pct"] = 45.0

    await strategy._evaluate_state(instrument, state, 105.0)
    assert state["internal_state"] == "BULLISH_TREND_CONFIRMED"

    # OI conviction flips hard bearish and price breaks the lower band.
    state["last_vwap"] = 100.0
    state["current_st"] = 110.0
    state["oi_diff_pct"] = -50.0
    await strategy._evaluate_state(instrument, state, 90.0)
    assert state["market_state"] == "TRENDING_BEARISH"
    assert state["internal_state"] == "BEARISH_TREND_CONFIRMED"


# --------------------------- Determinism ---------------------------

@pytest.mark.asyncio
async def test_identical_inputs_produce_identical_output(strategy):
    instrument = "NIFTY FUT"

    async def _run_once():
        s = strategy._get_instrument_state(f"{instrument}_{id(object())}")
        s["last_vwap"] = 100.0
        s["current_st"] = 90.0
        s["oi_diff_pct"] = 45.0
        await strategy._evaluate_state(instrument, s, 105.0)
        return s["market_state"], s["internal_state"], s["active_signal"]["type"]

    result_a = await _run_once()
    result_b = await _run_once()
    assert result_a == result_b
