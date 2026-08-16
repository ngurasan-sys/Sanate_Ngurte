import pytest
from backend.app.order_flow.engine import OrderFlowEngine
from backend.app.order_flow.analysis import calculate_trade_size, classify_trade_direction

def test_trade_size_reconciliation():
    # 1. LTQ only
    assert calculate_trade_size(10, None, None) == (10, 'LTQ', 'VALID')

    # 2. Cumulative only
    assert calculate_trade_size(None, 20, 10) == (10, 'CUMULATIVE', 'VALID')

    # 3. Both match
    assert calculate_trade_size(10, 20, 10) == (10, 'LTQ', 'VALID')

    # 4. Mismatch
    assert calculate_trade_size(15, 20, 10) == (15, 'LTQ', 'MISMATCH')

    # 5. Neither
    assert calculate_trade_size(None, None, None) == (0, 'NONE', 'UNKNOWN')
    assert calculate_trade_size(0, 10, 10) == (0, 'NONE', 'UNKNOWN')

def test_trade_classification():
    # Level 1 - Quote Rule
    assert classify_trade_direction(100, 99, 98, None) == "AGGRESSIVE_BUY"
    assert classify_trade_direction(97, 99, 98, None) == "AGGRESSIVE_SELL"

    # Level 2 - Tick Rule (inside spread)
    assert classify_trade_direction(98.5, 99, 98, 98.4) == "AGGRESSIVE_BUY"
    assert classify_trade_direction(98.5, 99, 98, 98.6) == "AGGRESSIVE_SELL"

    # Level 3 - Unknown
    assert classify_trade_direction(98.5, 99, 98, None) == "UNKNOWN"

def test_engine_incremental_update():
    engine = OrderFlowEngine()

    # Tick 1: Setup depth and first trade
    tick1 = {
        "instrument_key": "NIFTY",
        "ltt": 1000,
        "ltp": 100.0,
        "ltq": 50,
        "volume": 50,
        "market_depth": {
            "bids": [{"price": 99.0, "quantity": 100, "orders": 1}],
            "asks": [{"price": 101.0, "quantity": 100, "orders": 1}]
        }
    }
    state = engine.process_tick(tick1)

    assert state.instrument_key == "NIFTY"
    assert state.spread == 2.0
    assert state.mid_price == 100.0
    assert state.trade_size == 50
    assert state.classification_mode == "UNKNOWN"
    assert state.unknown_volume == 50
    assert state.buy_volume == 0
    assert state.sell_volume == 0

    # Tick 2: Aggressive buy
    tick2 = {
        "instrument_key": "NIFTY",
        "ltt": 1001,
        "ltp": 101.0,
        "ltq": 20,
        "volume": 70,
    }
    state = engine.process_tick(tick2)
    assert state.trade_size == 20
    assert state.classification_mode == "AGGRESSIVE_BUY"
    assert state.buy_volume == 20
    assert state.unknown_volume == 50
    assert state.bar_delta == 20
    assert state.cvd == 20
    assert state.footprint[101.0].ask_volume == 20

    # Tick 3: Aggressive sell
    tick3 = {
        "instrument_key": "NIFTY",
        "ltt": 1002,
        "ltp": 99.0,
        "ltq": 30,
        "volume": 100,
    }
    state = engine.process_tick(tick3)
    assert state.trade_size == 30
    assert state.classification_mode == "AGGRESSIVE_SELL"
    assert state.sell_volume == 30
    assert state.bar_delta == -10
    assert state.cvd == -10

    # Check footprint
    assert 101.0 in state.footprint
    assert 99.0 in state.footprint
    assert state.footprint[99.0].bid_volume == 30

def test_engine_greeks_update():
    engine = OrderFlowEngine()
    tick = {
        "instrument_key": "NIFTY_OPT",
        "ltt": 1000,
        "greeks": {
            "delta": 0.5,
            "gamma": 0.01,
            "vega": 10.0,
            "theta": -5.0,
            "iv": 0.15
        }
    }
    state = engine.process_tick(tick)
    assert state.greeks.delta == 0.5
    assert state.greeks.iv == 0.15

    # Partial update shouldn't overwrite existing
    tick2 = {
        "instrument_key": "NIFTY_OPT",
        "ltt": 1001,
        "greeks": {
            "delta": 0.6,
            "gamma": None
        }
    }
    state = engine.process_tick(tick2)
    assert state.greeks.delta == 0.6
    assert state.greeks.gamma == 0.01

def test_depth_imbalance():
    from backend.app.order_flow.models import DepthLevel
    from backend.app.order_flow.analysis import calculate_depth_imbalance

    # Using dicts now due to hot path optimizations
    bids = [{"price": 100, "quantity": 100, "orders": 1}, {"price": 99, "quantity": 200, "orders": 2}]
    asks = [{"price": 101, "quantity": 100, "orders": 1}, {"price": 102, "quantity": 50, "orders": 1}]

    # Imbalance 1: bid=100, ask=100, total=200 -> 0.0
    assert calculate_depth_imbalance(bids, asks, 1) == 0.0

    # Imbalance 2: bid=300, ask=150, total=450 -> 150/450 = 0.333...
    assert abs(calculate_depth_imbalance(bids, asks, 2) - 0.333) < 0.01

def test_spread_and_mid():
    from backend.app.order_flow.analysis import calculate_spread_and_mid

    assert calculate_spread_and_mid(100, 101) == (1.0, 100.5)
    assert calculate_spread_and_mid(100, 100) == (0.0, 100.0)
    assert calculate_spread_and_mid(101, 100) == (None, None) # Crossed
    assert calculate_spread_and_mid(None, 100) == (None, None)

def test_diagonal_imbalance():
    from backend.app.order_flow.models import FootprintNode
    from backend.app.order_flow.analysis import check_diagonal_imbalance

    footprint = {
        100.0: FootprintNode(price=100.0, bid_volume=10, ask_volume=0),
        101.0: FootprintNode(price=101.0, bid_volume=0, ask_volume=30),
        102.0: FootprintNode(price=102.0, bid_volume=5, ask_volume=10),
    }

    check_diagonal_imbalance(footprint, ratio=3.0)
    assert footprint[101.0].buy_imbalance is True
    assert footprint[102.0].buy_imbalance is False

def test_stacked_imbalance():
    from backend.app.order_flow.models import FootprintNode
    from backend.app.order_flow.analysis import check_stacked_imbalance

    footprint = {
        100.0: FootprintNode(price=100.0, buy_imbalance=True),
        101.0: FootprintNode(price=101.0, buy_imbalance=True),
        102.0: FootprintNode(price=102.0, buy_imbalance=True),
        103.0: FootprintNode(price=103.0, buy_imbalance=False),
    }

    check_stacked_imbalance(footprint, min_consecutive=3)
    assert footprint[100.0].stacked_zone == "BUY"
    assert footprint[101.0].stacked_zone == "BUY"
    assert footprint[102.0].stacked_zone == "BUY"
    assert footprint[103.0].stacked_zone is None


def test_stacked_imbalance_below_minimum_consecutive_is_not_marked():
    from backend.app.order_flow.models import FootprintNode
    from backend.app.order_flow.analysis import check_stacked_imbalance

    footprint = {
        100.0: FootprintNode(price=100.0, buy_imbalance=True),
        101.0: FootprintNode(price=101.0, buy_imbalance=True),
        102.0: FootprintNode(price=102.0, buy_imbalance=False),
    }

    check_stacked_imbalance(footprint, min_consecutive=3)
    assert footprint[100.0].stacked_zone is None
    assert footprint[101.0].stacked_zone is None


def test_stacked_imbalance_stack_running_to_the_end_is_still_flushed():
    """A stack that never hits a non-imbalanced level (runs off the end
    of the sorted price range) must still be marked — the flush-on-break
    logic alone would miss it.
    """
    from backend.app.order_flow.models import FootprintNode
    from backend.app.order_flow.analysis import check_stacked_imbalance

    footprint = {
        100.0: FootprintNode(price=100.0, sell_imbalance=True),
        101.0: FootprintNode(price=101.0, sell_imbalance=True),
        102.0: FootprintNode(price=102.0, sell_imbalance=True),
    }

    check_stacked_imbalance(footprint, min_consecutive=3)
    assert footprint[100.0].stacked_zone == "SELL"
    assert footprint[102.0].stacked_zone == "SELL"


def test_stacked_imbalance_resets_stale_markers_from_prior_call():
    from backend.app.order_flow.models import FootprintNode
    from backend.app.order_flow.analysis import check_stacked_imbalance

    footprint = {
        100.0: FootprintNode(price=100.0, buy_imbalance=True, stacked_zone="BUY"),
        101.0: FootprintNode(price=101.0, buy_imbalance=False, stacked_zone="BUY"),
    }

    check_stacked_imbalance(footprint, min_consecutive=3)
    assert footprint[101.0].stacked_zone is None

def test_negative_cumulative_delta():
    # cumulative delta is negative, which is impossible in a single session unless reset
    assert calculate_trade_size(None, 10, 20) == (0, 'NONE', 'UNKNOWN')

def test_equal_price_tick():
    engine = OrderFlowEngine()
    engine.process_tick({
        "instrument_key": "NIFTY",
        "ltp": 100.0,
        "ltq": 50,
        "volume": 50,
        "market_depth": {
            "bids": [{"price": 99.0, "quantity": 100, "orders": 1}],
            "asks": [{"price": 101.0, "quantity": 100, "orders": 1}]
        }
    })

    # Tick inside spread with equal price to previous, retains previous direction
    # First establish a direction
    engine.process_tick({
        "instrument_key": "NIFTY",
        "ltp": 100.5,
        "ltq": 10,
        "volume": 60,
    }) # AGGRESSIVE_BUY

    state = engine.process_tick({
        "instrument_key": "NIFTY",
        "ltp": 100.5,
        "ltq": 10,
        "volume": 70,
    })
    assert state.classification_mode == "AGGRESSIVE_BUY"

def test_missing_bid_ask():
    engine = OrderFlowEngine()
    state = engine.process_tick({
        "instrument_key": "NIFTY",
        "ltp": 100.0,
        "ltq": 50,
        "volume": 50,
        "market_depth": {
            "bids": [], # Missing bid
            "asks": [{"price": 101.0, "quantity": 100, "orders": 1}]
        }
    })
    assert state.spread is None
    assert state.mid_price is None

def test_duplicate_out_of_order_ticks():
    engine = OrderFlowEngine()

    # Base tick
    engine.process_tick({
        "instrument_key": "NIFTY",
        "ltt": 1000,
        "ltp": 100.0,
        "ltq": 50,
        "volume": 50,
        "market_depth": {
            "bids": [{"price": 99.0, "quantity": 100, "orders": 1}],
            "asks": [{"price": 101.0, "quantity": 100, "orders": 1}]
        }
    })

    # Duplicate tick - volume hasn't changed, no new trade
    state = engine.process_tick({
        "instrument_key": "NIFTY",
        "ltt": 1000,
        "ltp": 100.0,
        "ltq": 50,
        "volume": 50,
    })
    assert state.trade_size == 0

def test_no_execution_calls():
    engine = OrderFlowEngine()
    state = engine.process_tick({
        "instrument_key": "NIFTY",
        "ltp": 100.0,
        "ltq": 50,
        "volume": 50
    })
    assert state is not None
