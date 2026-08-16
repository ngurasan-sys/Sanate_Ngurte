import random

from backend.app.order_flow.mock_feed import MockFootprintFeed, _SEED_PRICES, TICK_SIZE


def test_generated_tick_has_the_expected_shape():
    random.seed(1)
    feed = MockFootprintFeed()
    tick = feed._generate_tick("NIFTY FUT")

    assert tick["instrument_key"] == "NIFTY FUT"
    assert isinstance(tick["price"], float)
    assert isinstance(tick["volume"], int)
    assert tick["direction"] in ("AGGRESSIVE_BUY", "AGGRESSIVE_SELL")
    assert tick["timestamp"] is not None


def test_price_snaps_to_tick_size():
    random.seed(2)
    feed = MockFootprintFeed()
    for _ in range(50):
        tick = feed._generate_tick("NIFTY FUT")
        # price / TICK_SIZE should land on (very close to) an integer
        remainder = round(tick["price"] / TICK_SIZE) * TICK_SIZE - tick["price"]
        assert abs(remainder) < 1e-6


def test_price_stays_near_seed_after_many_ticks_no_runaway_walk():
    random.seed(3)
    feed = MockFootprintFeed()
    for _ in range(500):
        feed._generate_tick("NIFTY FUT")
    # A bounded random walk over 500 small ticks shouldn't wander far
    # from the seed — this is a sanity check against a runaway drift bug,
    # not a precise statistical claim.
    assert abs(feed._prices["NIFTY FUT"] - _SEED_PRICES["NIFTY FUT"]) < 500


def test_burst_produces_several_consecutive_same_direction_ticks():
    random.seed(4)
    feed = MockFootprintFeed()
    # Force a burst to start deterministically.
    feed._burst["NIFTY FUT"]["ticks_left"] = 5
    feed._burst["NIFTY FUT"]["direction"] = "AGGRESSIVE_BUY"

    directions = [feed._generate_tick("NIFTY FUT")["direction"] for _ in range(5)]
    assert directions == ["AGGRESSIVE_BUY"] * 5


def test_all_three_seed_instruments_generate_independently():
    random.seed(5)
    feed = MockFootprintFeed()
    for instrument in _SEED_PRICES:
        tick = feed._generate_tick(instrument)
        assert tick["instrument_key"] == instrument


def test_mock_ticks_publish_on_their_own_isolated_channel_not_market_tick():
    """The whole point of keeping this on its own channel: simulated data
    must never be able to reach a real strategy engine subscribed to
    MARKET_TICK.
    """
    import inspect
    from backend.app.order_flow import mock_feed as mock_feed_module

    source = inspect.getsource(mock_feed_module.MockFootprintFeed._run_loop)
    assert '"footprint_mock_tick"' in source
    assert '"MARKET_TICK"' not in source
