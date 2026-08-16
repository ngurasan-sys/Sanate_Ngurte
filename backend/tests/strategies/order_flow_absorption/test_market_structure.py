from backend.app.strategies.order_flow_absorption.market_structure import (
    StructureBar, StructureBias, SwingType, classify_structure,
    find_swing_points, is_holding_above, is_holding_below, resample_bars,
)


def bar(high, low, close):
    return StructureBar(high=high, low=low, close=close)


def test_find_swing_points_identifies_a_simple_high_and_low():
    bars = [
        bar(100, 95, 98), bar(102, 97, 100), bar(110, 99, 105),  # swing high at idx 2
        bar(103, 98, 100), bar(101, 96, 99),
        bar(100, 90, 95), bar(102, 92, 96),  # swing low at idx 5
        bar(104, 94, 100), bar(106, 96, 102),
    ]
    swings = find_swing_points(bars, lookback=2)
    highs = [s for s in swings if s.type == SwingType.HIGH]
    lows = [s for s in swings if s.type == SwingType.LOW]
    assert any(s.index == 2 and s.price == 110 for s in highs)
    assert any(s.index == 5 and s.price == 90 for s in lows)


def test_find_swing_points_never_classifies_the_trailing_lookback_bars():
    bars = [bar(100 + i, 90 + i, 95 + i) for i in range(6)]
    swings = find_swing_points(bars, lookback=2)
    assert all(s.index < len(bars) - 2 for s in swings)


def test_classify_structure_bullish_on_higher_highs_and_higher_lows():
    # Two clear upward swing legs: low@90 -> high@110 -> higher low@95 -> higher high@120
    bars = [
        bar(100, 95, 98), bar(102, 97, 100), bar(90, 88, 92),   # swing low ~idx2 (90)
        bar(95, 91, 93), bar(100, 94, 98), bar(110, 100, 108),  # swing high ~idx5 (110)
        bar(105, 99, 102), bar(98, 95, 97), bar(96, 93, 95),    # swing low ~idx8 (93 area)...
    ]
    # Build a cleaner, deterministic bullish structure explicitly:
    bullish_bars = [
        bar(100, 90, 95), bar(102, 92, 96), bar(90, 85, 88), bar(92, 87, 90), bar(94, 89, 91),  # low1=85 @ idx2
        bar(105, 95, 100), bar(112, 96, 108), bar(108, 98, 104), bar(106, 97, 103), bar(104, 96, 101),  # high1=112 @ idx6
        bar(100, 92, 95), bar(98, 90, 93), bar(89, 86, 87), bar(91, 87, 89), bar(93, 88, 90),  # low2=86 @ idx12
        bar(110, 100, 105), bar(120, 102, 118), bar(115, 105, 110), bar(112, 103, 108), bar(109, 101, 106),  # high2=120 @ idx16
    ]
    result = classify_structure(bullish_bars, lookback=2)
    assert result == StructureBias.BULLISH


def test_classify_structure_bearish_on_lower_highs_and_lower_lows():
    bearish_bars = [
        bar(120, 110, 115), bar(118, 108, 112), bar(130, 120, 128), bar(122, 112, 118), bar(119, 109, 113),  # high1=130 @ idx2
        bar(105, 95, 100), bar(95, 85, 92), bar(100, 90, 95), bar(103, 93, 98), bar(106, 96, 101),  # low1=85 @ idx6
        bar(115, 105, 110), bar(118, 108, 114), bar(112, 102, 106), bar(108, 100, 103), bar(105, 97, 100),  # high2=118 @ idx11
        bar(95, 85, 90), bar(85, 75, 80), bar(88, 78, 83), bar(90, 80, 85), bar(92, 82, 87),  # low2=75 @ idx16
    ]
    result = classify_structure(bearish_bars, lookback=2)
    assert result == StructureBias.BEARISH


def test_classify_structure_unknown_with_insufficient_swings():
    bars = [bar(100, 95, 98) for _ in range(3)]
    assert classify_structure(bars, lookback=2) == StructureBias.UNKNOWN


def test_classify_structure_balanced_on_mixed_signals():
    # Higher high but lower low -> neither bullish nor bearish pattern.
    mixed_bars = [
        bar(100, 90, 95), bar(102, 92, 96), bar(90, 85, 88), bar(92, 87, 90), bar(94, 89, 91),  # low1=85 @ idx2
        bar(105, 95, 100), bar(112, 96, 108), bar(108, 98, 104), bar(106, 97, 103), bar(104, 96, 101),  # high1=112 @ idx6
        bar(100, 92, 95), bar(98, 90, 93), bar(80, 70, 75), bar(85, 75, 78), bar(88, 78, 80),  # low2=70 (LOWER than 85) @ idx12
        bar(110, 100, 105), bar(120, 102, 118), bar(115, 105, 110), bar(112, 103, 108), bar(109, 101, 106),  # high2=120 (HIGHER) @ idx16
    ]
    result = classify_structure(mixed_bars, lookback=2)
    assert result == StructureBias.BALANCED


def test_is_holding_above_requires_all_recent_closes_above_reference():
    bars = [bar(105, 100, 102), bar(106, 101, 103), bar(107, 102, 104)]
    assert is_holding_above(bars, reference_price=101, min_closes=3) is True
    assert is_holding_above(bars, reference_price=103, min_closes=3) is False


def test_is_holding_above_false_when_not_enough_bars():
    bars = [bar(105, 100, 102)]
    assert is_holding_above(bars, reference_price=100, min_closes=3) is False


def test_is_holding_below_mirrors_is_holding_above():
    bars = [bar(105, 100, 98), bar(104, 99, 97), bar(103, 98, 96)]
    assert is_holding_below(bars, reference_price=99, min_closes=3) is True
    assert is_holding_below(bars, reference_price=96, min_closes=3) is False


def test_resample_bars_rolls_up_groups():
    quarter_bars = [bar(100, 95, 98), bar(103, 96, 101), bar(105, 97, 100), bar(99, 94, 96)]
    resampled = resample_bars(quarter_bars, group_size=4)
    assert len(resampled) == 1
    assert resampled[0].high == 105
    assert resampled[0].low == 94
    assert resampled[0].close == 96


def test_resample_bars_drops_a_trailing_partial_group():
    bars = [bar(100, 95, 98)] * 5  # 5 bars, group_size 4 -> 1 full group, 1 leftover dropped
    resampled = resample_bars(bars, group_size=4)
    assert len(resampled) == 1
