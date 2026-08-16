from datetime import datetime, timezone

from backend.app.order_flow.footprint_candle import FootprintCandleAggregator, floor_to_timeframe


def _dt(minute, second=0):
    return datetime(2024, 10, 1, 9, minute, second, tzinfo=timezone.utc)


def test_floor_to_timeframe_buckets_into_5_minute_windows():
    assert floor_to_timeframe(_dt(17, 43), "5m") == _dt(15)
    assert floor_to_timeframe(_dt(15, 0), "5m") == _dt(15)
    assert floor_to_timeframe(_dt(19, 59), "5m") == _dt(15)


def test_first_tick_opens_a_new_candle_with_ohlc_all_equal_to_that_price():
    agg = FootprintCandleAggregator()
    candle = agg.process_tick("NIFTY FUT", 24500.0, 100, "AGGRESSIVE_BUY", _dt(15, 1), "5m")
    assert candle.open == candle.high == candle.low == candle.close == 24500.0
    assert candle.is_closed is False


def test_ohlc_updates_within_the_same_bucket():
    agg = FootprintCandleAggregator()
    agg.process_tick("NIFTY FUT", 24500.0, 100, "AGGRESSIVE_BUY", _dt(15, 1), "5m")
    agg.process_tick("NIFTY FUT", 24510.0, 100, "AGGRESSIVE_BUY", _dt(16, 0), "5m")
    candle = agg.process_tick("NIFTY FUT", 24490.0, 100, "AGGRESSIVE_SELL", _dt(19, 30), "5m")

    assert candle.open == 24500.0
    assert candle.high == 24510.0
    assert candle.low == 24490.0
    assert candle.close == 24490.0


def test_tick_in_a_new_bucket_closes_the_old_candle_and_opens_a_new_one():
    agg = FootprintCandleAggregator()
    agg.process_tick("NIFTY FUT", 24500.0, 100, "AGGRESSIVE_BUY", _dt(15, 1), "5m")
    new_candle = agg.process_tick("NIFTY FUT", 24600.0, 100, "AGGRESSIVE_BUY", _dt(20, 5), "5m")

    assert new_candle.open == 24600.0
    history = agg.get_history("NIFTY FUT", "5m")
    assert len(history) == 1
    assert history[0].is_closed is True
    assert history[0].close == 24500.0


def test_buy_volume_goes_to_ask_volume_and_sell_to_bid_volume():
    agg = FootprintCandleAggregator()
    candle = agg.process_tick("NIFTY FUT", 24500.0, 100, "AGGRESSIVE_BUY", _dt(15, 1), "5m")
    candle = agg.process_tick("NIFTY FUT", 24500.0, 40, "AGGRESSIVE_SELL", _dt(15, 2), "5m")

    node = candle.footprint[24500.0]
    assert node.ask_volume == 100
    assert node.bid_volume == 40
    assert node.total_volume == 140
    assert node.delta == 60
    assert candle.buy_volume == 100
    assert candle.sell_volume == 40
    assert candle.delta == 60


def test_poc_price_is_the_level_with_the_most_total_volume():
    agg = FootprintCandleAggregator()
    agg.process_tick("NIFTY FUT", 24500.0, 500, "AGGRESSIVE_BUY", _dt(15, 1), "5m")
    candle = agg.process_tick("NIFTY FUT", 24505.0, 50, "AGGRESSIVE_BUY", _dt(15, 2), "5m")
    assert candle.poc_price == 24500.0


def test_diagonal_imbalance_is_flagged_within_a_candle():
    agg = FootprintCandleAggregator(imbalance_ratio_pct=300.0)
    agg.process_tick("NIFTY FUT", 24500.0, 10, "AGGRESSIVE_SELL", _dt(15, 1), "5m")  # bid_volume=10 @ 24500
    candle = agg.process_tick("NIFTY FUT", 24500.05, 40, "AGGRESSIVE_BUY", _dt(15, 2), "5m")  # ask_volume=40 @ 24500.05

    # 40 >= 3.0 * 10 -> diagonal buy imbalance at the higher price level
    assert candle.footprint[24500.05].buy_imbalance is True


def test_raising_imbalance_ratio_can_suppress_a_previously_flagged_imbalance():
    low_ratio_agg = FootprintCandleAggregator(imbalance_ratio_pct=200.0)
    low_ratio_agg.process_tick("NIFTY FUT", 24500.0, 10, "AGGRESSIVE_SELL", _dt(15, 1), "5m")
    low_candle = low_ratio_agg.process_tick("NIFTY FUT", 24500.05, 25, "AGGRESSIVE_BUY", _dt(15, 2), "5m")
    assert low_candle.footprint[24500.05].buy_imbalance is True  # 25 >= 2.0 * 10

    high_ratio_agg = FootprintCandleAggregator(imbalance_ratio_pct=500.0)
    high_ratio_agg.process_tick("NIFTY FUT", 24500.0, 10, "AGGRESSIVE_SELL", _dt(15, 1), "5m")
    high_candle = high_ratio_agg.process_tick("NIFTY FUT", 24500.05, 25, "AGGRESSIVE_BUY", _dt(15, 2), "5m")
    assert high_candle.footprint[24500.05].buy_imbalance is False  # 25 < 5.0 * 10


def test_stacked_imbalance_zone_marked_across_three_consecutive_levels():
    agg = FootprintCandleAggregator(imbalance_ratio_pct=300.0, stacked_min_consecutive=3)
    ts = _dt(15, 1)
    # Build three consecutive diagonally-imbalanced buy levels: 100/101/102
    # each need ask_volume >= 3x the bid_volume one tick below.
    agg.process_tick("NIFTY FUT", 100.0, 10, "AGGRESSIVE_SELL", ts, "5m")
    agg.process_tick("NIFTY FUT", 101.0, 40, "AGGRESSIVE_BUY", ts, "5m")
    agg.process_tick("NIFTY FUT", 101.0, 10, "AGGRESSIVE_SELL", ts, "5m")
    agg.process_tick("NIFTY FUT", 102.0, 40, "AGGRESSIVE_BUY", ts, "5m")
    agg.process_tick("NIFTY FUT", 102.0, 10, "AGGRESSIVE_SELL", ts, "5m")
    candle = agg.process_tick("NIFTY FUT", 103.0, 40, "AGGRESSIVE_BUY", ts, "5m")

    assert candle.footprint[101.0].stacked_zone == "BUY"
    assert candle.footprint[102.0].stacked_zone == "BUY"
    assert candle.footprint[103.0].stacked_zone == "BUY"
    assert candle.footprint[100.0].stacked_zone is None


def test_multiple_timeframes_tracked_independently_for_the_same_instrument():
    agg = FootprintCandleAggregator()
    agg.process_tick("NIFTY FUT", 24500.0, 100, "AGGRESSIVE_BUY", _dt(15, 1), "1m")
    agg.process_tick("NIFTY FUT", 24500.0, 100, "AGGRESSIVE_BUY", _dt(15, 1), "5m")

    assert agg.get_current("NIFTY FUT", "1m").timeframe == "1m"
    assert agg.get_current("NIFTY FUT", "5m").timeframe == "5m"


def test_multiple_instruments_tracked_independently():
    agg = FootprintCandleAggregator()
    agg.process_tick("NIFTY FUT", 24500.0, 100, "AGGRESSIVE_BUY", _dt(15, 1), "5m")
    agg.process_tick("SENSEX FUT", 80000.0, 50, "AGGRESSIVE_SELL", _dt(15, 1), "5m")

    assert agg.get_current("NIFTY FUT", "5m").close == 24500.0
    assert agg.get_current("SENSEX FUT", "5m").close == 80000.0


def test_history_is_bounded_by_max_history():
    agg = FootprintCandleAggregator(max_history=2)
    for i in range(5):
        agg.process_tick("NIFTY FUT", 24500.0 + i, 10, "AGGRESSIVE_BUY", _dt(15 + i * 5, 0), "5m")

    assert len(agg.get_history("NIFTY FUT", "5m")) == 2
