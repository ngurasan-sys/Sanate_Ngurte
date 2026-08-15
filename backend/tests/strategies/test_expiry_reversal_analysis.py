from datetime import time

from backend.app.strategies.expiry_reversal.analysis import (
    compute_breakout_stop_loss,
    compute_partial_exit_lots,
    compute_tier_prices,
    detect_oi_shift,
    is_structural_break,
    is_weak_bearish_move,
    is_weak_bullish_move,
    parse_hhmm,
    should_skip_late_session_trade,
)


def test_weak_bullish_move_short_covering_and_small_candle():
    assert is_weak_bullish_move(
        futures_classification="SHORT_COVERING",
        candle_body=5.0,
        daily_atr=100.0,
        body_atr_ratio_threshold=0.3,
    ) is True


def test_not_weak_when_long_buildup():
    assert is_weak_bullish_move(
        futures_classification="LONG_BUILDUP",
        candle_body=5.0,
        daily_atr=100.0,
        body_atr_ratio_threshold=0.3,
    ) is False


def test_not_weak_when_candle_body_large():
    assert is_weak_bullish_move(
        futures_classification="SHORT_COVERING",
        candle_body=50.0,
        daily_atr=100.0,
        body_atr_ratio_threshold=0.3,
    ) is False


def test_weak_bullish_move_zero_atr_is_never_weak():
    assert is_weak_bullish_move(
        futures_classification="SHORT_COVERING",
        candle_body=5.0,
        daily_atr=0.0,
        body_atr_ratio_threshold=0.3,
    ) is False


def test_weak_bearish_move_long_unwinding():
    assert is_weak_bearish_move(
        futures_classification="LONG_UNWINDING",
        candle_body=-5.0,
        daily_atr=100.0,
        body_atr_ratio_threshold=0.3,
    ) is True


def test_detect_oi_shift_bearish():
    bearish, bullish = detect_oi_shift(
        ce_oi_now=15_000_000, ce_oi_before=13_000_000,
        pe_oi_now=7_800_000, pe_oi_before=13_100_000,
        call_oi_increase_threshold=1_000_000, put_oi_decrease_threshold=1_000_000,
    )
    assert bearish is True
    assert bullish is False


def test_detect_oi_shift_bullish():
    bearish, bullish = detect_oi_shift(
        ce_oi_now=8_000_000, ce_oi_before=13_000_000,
        pe_oi_now=15_000_000, pe_oi_before=13_100_000,
        call_oi_increase_threshold=1_000_000, put_oi_decrease_threshold=1_000_000,
    )
    assert bullish is True
    assert bearish is False


def test_detect_oi_shift_below_threshold_is_neither():
    bearish, bullish = detect_oi_shift(
        ce_oi_now=13_100_000, ce_oi_before=13_000_000,
        pe_oi_now=13_050_000, pe_oi_before=13_100_000,
        call_oi_increase_threshold=1_000_000, put_oi_decrease_threshold=1_000_000,
    )
    assert bearish is False
    assert bullish is False


def test_structural_break_bearish_two_red_candles_breaking_low():
    assert is_structural_break(
        closes=[100.0, 90.0],
        opens=[105.0, 95.0],
        day_low=95.0,
        day_high=120.0,
        direction="BEARISH",
        min_candles=2,
    ) is True


def test_structural_break_fails_if_not_all_red():
    assert is_structural_break(
        closes=[100.0, 96.0],
        opens=[105.0, 90.0],  # second candle is green (close > open)
        day_low=95.0,
        day_high=120.0,
        direction="BEARISH",
        min_candles=2,
    ) is False


def test_structural_break_fails_if_low_not_broken():
    assert is_structural_break(
        closes=[100.0, 96.0],
        opens=[105.0, 98.0],
        day_low=95.0,
        day_high=120.0,
        direction="BEARISH",
        min_candles=2,
    ) is False


def test_skip_late_session_when_not_expiry_day():
    skip, reason = should_skip_late_session_trade(
        is_expiry_day=False,
        current_time=time(14, 30),
        late_session_start=time(14, 0),
        intraday_range=260.0,
        daily_atr=270.0,
        atr_exhaustion_ratio=0.95,
    )
    assert skip is False
    assert reason == ""


def test_skip_late_session_before_cutoff_time():
    skip, reason = should_skip_late_session_trade(
        is_expiry_day=True,
        current_time=time(11, 0),
        late_session_start=time(14, 0),
        intraday_range=260.0,
        daily_atr=270.0,
        atr_exhaustion_ratio=0.95,
    )
    assert skip is False


def test_skip_late_session_expiry_day_atr_exhausted():
    skip, reason = should_skip_late_session_trade(
        is_expiry_day=True,
        current_time=time(14, 30),
        late_session_start=time(14, 0),
        intraday_range=260.0,
        daily_atr=270.0,
        atr_exhaustion_ratio=0.95,
    )
    assert skip is True
    assert "expiry day" in reason.lower()
    assert "96%" in reason


def test_no_skip_expiry_day_but_atr_not_exhausted():
    skip, reason = should_skip_late_session_trade(
        is_expiry_day=True,
        current_time=time(14, 30),
        late_session_start=time(14, 0),
        intraday_range=100.0,
        daily_atr=270.0,
        atr_exhaustion_ratio=0.95,
    )
    assert skip is False


def test_compute_tier_prices_bearish():
    t1, t2, t3 = compute_tier_prices(
        breakout_price=24000.0, direction="BEARISH",
        tier_2_offset_points=10.0, tier_3_offset_points=25.0,
    )
    assert t1 == 24000.0
    assert t2 == 23990.0
    assert t3 == 23975.0


def test_compute_tier_prices_bullish():
    t1, t2, t3 = compute_tier_prices(
        breakout_price=24000.0, direction="BULLISH",
        tier_2_offset_points=10.0, tier_3_offset_points=25.0,
    )
    assert t1 == 24000.0
    assert t2 == 24010.0
    assert t3 == 24025.0


def test_compute_breakout_stop_loss_bearish_above_candle_high():
    sl = compute_breakout_stop_loss(
        breakout_candle_high=24050.0, breakout_candle_low=23980.0,
        direction="BEARISH", buffer_points=5.0,
    )
    assert sl == 24055.0


def test_compute_breakout_stop_loss_bullish_below_candle_low():
    sl = compute_breakout_stop_loss(
        breakout_candle_high=24050.0, breakout_candle_low=23980.0,
        direction="BULLISH", buffer_points=5.0,
    )
    assert sl == 23975.0


def test_compute_partial_exit_lots_rounds_down_min_one():
    assert compute_partial_exit_lots(lots_held=2, partial_exit_pct=50.0) == 1
    assert compute_partial_exit_lots(lots_held=8, partial_exit_pct=50.0) == 4
    assert compute_partial_exit_lots(lots_held=1, partial_exit_pct=10.0) == 1


def test_compute_partial_exit_lots_zero_when_no_position():
    assert compute_partial_exit_lots(lots_held=0, partial_exit_pct=50.0) == 0


def test_parse_hhmm():
    assert parse_hhmm("14:00") == time(14, 0)
    assert parse_hhmm("09:15") == time(9, 15)
