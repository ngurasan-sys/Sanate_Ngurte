"""End-to-end test of OFAOEngine's pipeline: seeds a fresh
FootprintCandleAggregator directly (bypassing tick replay for
determinism/speed — the aggregator's own tick-to-candle math is already
covered by test_footprint_candle.py) with a synthetic bullish structure
+ seller-absorption + buyer-dominance sequence, then drives the engine
through LOCATION_REACHED -> ... -> SIGNAL_READY -> a real DECISION_CREATED
publish, proving the whole chain actually wires together.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.order_flow.footprint_candle import FootprintCandle, FootprintCandleAggregator
from backend.app.order_flow.models import FootprintNode
from backend.app.strategies.order_flow_absorption.config import OFAOConfig
from backend.app.strategies.order_flow_absorption.engine import OFAOEngine
from backend.app.strategies.order_flow_absorption.models import SetupState

BASE = datetime(2024, 10, 1, 6, 0, tzinfo=timezone.utc)  # ~11:30 IST — safely inside the default entry window
INSTRUMENT = "NIFTY FUT"


def _node(price, bid, ask):
    return FootprintNode(price=price, bid_volume=bid, ask_volume=ask, total_volume=bid + ask, delta=ask - bid)


def _candle(open_time, open_, high, low, close, footprint, timeframe="5m"):
    return FootprintCandle(
        instrument_key=INSTRUMENT, timeframe=timeframe, open_time=open_time,
        open=open_, high=high, low=low, close=close, is_closed=True,
        footprint=footprint,
        buy_volume=sum(n.ask_volume for n in footprint.values()),
        sell_volume=sum(n.bid_volume for n in footprint.values()),
        delta=sum(n.ask_volume - n.bid_volume for n in footprint.values()),
    )


def _bullish_structure_bars(timeframe="15m"):
    """20 fifteen-minute bars forming higher-highs + higher-lows, matching
    the fixture already proven correct in test_market_structure.py.
    """
    quads = [
        (100, 90, 95), (102, 92, 96), (90, 85, 88), (92, 87, 90), (94, 89, 91),
        (105, 95, 100), (112, 96, 108), (108, 98, 104), (106, 97, 103), (104, 96, 101),
        (100, 92, 95), (98, 90, 93), (89, 86, 87), (91, 87, 89), (93, 88, 90),
        (110, 100, 105), (120, 102, 118), (115, 105, 110), (112, 103, 108), (109, 101, 106),
    ]
    bars = []
    for i, (h, l, c) in enumerate(quads):
        bars.append(_candle(BASE + timedelta(minutes=15 * i), c, h, l, c, {c: _node(c, 10, 10)}, timeframe=timeframe))
    return bars


@pytest.fixture
def engine():
    config = OFAOConfig(
        enabled=True,
        absorption_strength_threshold=1.0,   # deterministic test, not tuning the scoring weights here
        location_proximity_pct=0.01,          # 1% — realistic-ish, tight enough to not also trigger the middle-of-value veto
        min_absorption_candles=2,
        absorption_window_candles=3,
        absorption_max_break_pct=0.02,  # synthetic fixture's ~1.2% break needs more room than the 0.5% default
        dominance_window_candles=3,
        signal_timeout_seconds=999,
        max_underlying_drift_pct=1.0,
        imbalance_ratio_pct=300.0,
        risk_reward_min=1.0,
        entry_start_time="00:00",
        entry_cutoff_time="23:59",
        # group_size=1 makes resample_bars an identity op, so the
        # already-validated bullish fixture (test_market_structure.py)
        # is classified directly rather than being further collapsed
        # into fewer, differently-shaped "1H"/"4H" bars.
        structure_1h_bars=1,
        structure_4h_bars=1,
    )
    return OFAOEngine(config=config)


@pytest.fixture
def seeded_aggregator():
    """A fresh, isolated aggregator (not the shared footprint_processor
    singleton) seeded with 15m structure bars and empty 5m history — the
    test itself appends 5m candles as the setup progresses.
    """
    agg = FootprintCandleAggregator()
    structure_bars = _bullish_structure_bars("15m")
    agg._history[INSTRUMENT] = {"15m": structure_bars, "5m": []}
    return agg


def test_scan_finds_no_setup_with_unknown_context(engine, seeded_aggregator):
    seeded_aggregator._history[INSTRUMENT]["15m"] = []  # no structure data -> UNKNOWN
    with patch("backend.app.strategies.order_flow_absorption.engine.footprint_processor") as mock_fp:
        mock_fp.aggregator = seeded_aggregator
        engine._scan_for_new_setup(INSTRUMENT, "NIFTY", [_candle(BASE, 100, 101, 99, 100, {100: _node(100, 5, 5)})], BASE)
    assert engine.state_machine.get(INSTRUMENT).state == SetupState.NO_SETUP


def test_scan_reaches_location_with_bullish_context(engine, seeded_aggregator):
    # Multi-level footprint so the volume profile has real spread
    # (POC/VAH/VAL don't all degenerate to one price the way a
    # single-node footprint would) — bulk of volume sits higher up
    # (~90), price at 86 sits near the value area's low edge, a
    # genuine discount rather than an accidental "middle of value".
    candle = _candle(BASE, 86, 87, 85, 86, {
        86.0: _node(86.0, 5, 5), 88.0: _node(88.0, 10, 10),
        90.0: _node(90.0, 50, 50), 92.0: _node(92.0, 10, 10),
    })
    with patch("backend.app.strategies.order_flow_absorption.engine.footprint_processor") as mock_fp:
        mock_fp.aggregator = seeded_aggregator
        engine._scan_for_new_setup(INSTRUMENT, "NIFTY", [candle], BASE)
    ctx = engine.state_machine.get(INSTRUMENT)
    assert ctx.state == SetupState.LOCATION_REACHED
    assert ctx.setup_id is not None
    assert ctx.setup_id.startswith("NIFTY_")


@pytest.mark.asyncio
async def test_full_pipeline_reaches_signal_ready_and_publishes_decision_created(engine, seeded_aggregator):
    with patch("backend.app.strategies.order_flow_absorption.engine.footprint_processor") as mock_fp:
        mock_fp.aggregator = seeded_aggregator

        # 1. LOCATION_REACHED — multi-level footprint so the volume
        # profile doesn't degenerate to a single price (see the sibling
        # test's comment for why).
        location_candle = _candle(BASE, 86, 87, 85, 86, {
            86.0: _node(86.0, 5, 5), 88.0: _node(88.0, 10, 10),
            90.0: _node(90.0, 50, 50), 92.0: _node(92.0, 10, 10),
        })
        engine._scan_for_new_setup(INSTRUMENT, "NIFTY", [location_candle], BASE)
        assert engine.state_machine.get(INSTRUMENT).state == SetupState.LOCATION_REACHED

        # 2. ABSORPTION_DETECTED — heavy aggressive selling defends 85, price never breaks it
        absorption_candles = []
        t = BASE + timedelta(minutes=5)
        for i in range(3):
            fp = {
                85.0: _node(85.0, bid=800, ask=100),
                85.5: _node(85.5, bid=100, ask=300),
            }
            absorption_candles.append(_candle(t + timedelta(minutes=5 * i), 86, 86.5, 85.0, 86.2, fp))
        all_candles = [location_candle] + absorption_candles
        engine._evaluate_absorption(INSTRUMENT, engine.state_machine.get(INSTRUMENT), all_candles, all_candles[-1].open_time)
        ctx = engine.state_machine.get(INSTRUMENT)
        assert ctx.state == SetupState.ABSORPTION_DETECTED
        assert ctx.absorption_strength > 0

        # -> WAITING_FOR_DOMINANCE (pass-through transition)
        engine.state_machine.transition(INSTRUMENT, SetupState.WAITING_FOR_DOMINANCE, now=all_candles[-1].open_time)

        # 3. DOMINANCE_CONFIRMED — buyers aggressive, ask-side imbalance, break above absorption high (86.5)
        dominance_time = absorption_candles[-1].open_time + timedelta(minutes=5)
        dominance_fp = {
            86.5: _node(86.5, bid=10, ask=5),
            87.0: _node(87.0, bid=0, ask=50),  # 50 >= 3x*10 -> ask-side imbalance at ratio 300%
        }
        dominance_candle = _candle(dominance_time, 86.5, 87.2, 86.4, 87.1, dominance_fp)
        engine._evaluate_dominance(INSTRUMENT, ctx, all_candles + [dominance_candle], dominance_time)
        ctx = engine.state_machine.get(INSTRUMENT)
        assert ctx.state == SetupState.DOMINANCE_CONFIRMED

        # 4. SIGNAL_READY
        engine._build_signal(INSTRUMENT, "NIFTY", ctx, all_candles + [dominance_candle], dominance_time)
        ctx = engine.state_machine.get(INSTRUMENT)
        assert ctx.state == SetupState.SIGNAL_READY
        assert ctx.trade_intent is not None
        assert ctx.trade_intent.option_type == "CE"
        assert ctx.trade_intent.risk_reward >= engine.config.risk_reward_min

        # 5. Execute: mock the broker-facing pieces (token, option chain),
        # verify a real DECISION_CREATED gets published with source="OFAO".
        published = []

        async def _fake_publish(channel, payload):
            published.append((channel, payload))

        fake_chain = [{
            "strike_price": ctx.trade_intent.strike,
            "call_options": {
                "instrument_key": "NSE_FO|NIFTY25000CE",
                "market_data": {"bid_price": 100.0, "ask_price": 101.0, "ltp": 100.5, "volume": 5000, "oi": 20000},
                "option_greeks": {"iv": 0.15, "delta": 0.5, "gamma": 0.01, "theta": -1.0, "vega": 5.0},
            },
        }]

        with patch("backend.app.strategies.order_flow_absorption.engine.upstox_auth.load_token", return_value="fake-token"), \
             patch("backend.app.strategies.order_flow_absorption.engine.fetch_option_chain", new=AsyncMock(return_value=fake_chain)), \
             patch("backend.app.strategies.order_flow_absorption.engine.event_bus.publish", side_effect=_fake_publish):
            await engine._execute_signal(INSTRUMENT, "NIFTY", ctx, all_candles + [dominance_candle], dominance_time)

        ctx = engine.state_machine.get(INSTRUMENT)
        assert ctx.state == SetupState.ORDER_SUBMITTED
        assert len(published) == 1
        channel, payload = published[0]
        assert channel == "DECISION_CREATED"
        assert payload["source"] == "OFAO"
        assert payload["transaction_type"] == "BUY"
        assert payload["quantity"] > 0
        assert payload["decision_id"] == f"OFAO_{ctx.setup_id}"


@pytest.mark.asyncio
async def test_stale_signal_is_cancelled_not_executed(engine, seeded_aggregator):
    engine.config.signal_timeout_seconds = 1.0
    with patch("backend.app.strategies.order_flow_absorption.engine.footprint_processor") as mock_fp:
        mock_fp.aggregator = seeded_aggregator
        location_candle = _candle(BASE, 86, 87, 85, 86, {
            86.0: _node(86.0, 5, 5), 88.0: _node(88.0, 10, 10),
            90.0: _node(90.0, 50, 50), 92.0: _node(92.0, 10, 10),
        })
        engine._scan_for_new_setup(INSTRUMENT, "NIFTY", [location_candle], BASE)
        ctx = engine.state_machine.get(INSTRUMENT)
        assert ctx.state == SetupState.LOCATION_REACHED
        engine.state_machine.transition(INSTRUMENT, SetupState.ABSORPTION_DETECTED, now=BASE, absorption_strength=90.0, invalidation_price=85.0)
        engine.state_machine.transition(INSTRUMENT, SetupState.WAITING_FOR_DOMINANCE, now=BASE)
        engine.state_machine.transition(INSTRUMENT, SetupState.DOMINANCE_CONFIRMED, now=BASE)
        from backend.app.strategies.order_flow_absorption.models import TradeIntent
        intent = TradeIntent(
            setup_id=ctx.setup_id, timestamp=BASE, underlying="NIFTY", direction="BUY", option_type="CE",
            strike=25000, expiry="UNRESOLVED", quantity=0, underlying_trigger=86.0, underlying_stop=85.0,
            underlying_target=88.0, risk_reward=2.0, score=11, confidence="A+", reason="test",
            location="test", absorption_strength=90.0, imbalance_ratio_pct=300.0,
        )
        engine.state_machine.transition(INSTRUMENT, SetupState.SIGNAL_READY, now=BASE, trade_intent=intent)

        way_later = BASE + timedelta(seconds=10)
        await engine._execute_signal(INSTRUMENT, "NIFTY", engine.state_machine.get(INSTRUMENT), [location_candle], way_later)

    assert engine.state_machine.get(INSTRUMENT).state == SetupState.NO_SETUP  # cancelled + reset


def test_disabled_config_skips_evaluation_entirely(engine):
    engine.config.enabled = False

    async def _run():
        await engine.evaluate(INSTRUMENT, "NIFTY")
    import asyncio
    asyncio.run(_run())
    assert engine.state_machine.get(INSTRUMENT).state == SetupState.NO_SETUP
