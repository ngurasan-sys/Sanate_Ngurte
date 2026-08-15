"""Engine tests, mirroring test_risk_execution_chain.py's style: patch
event_bus.publish and inspect what actually got published, plus patch the
network boundary (token + option chain fetch) so nothing here touches a
real broker.

Since place_order/add_pyramid/close_position no longer assume success —
they submit a DECISION_CREATED and wait for RISK_DECISION/EXECUTION_UPDATE
to actually confirm the outcome — these tests drive that confirmation step
manually via engine._on_execution_update(...)/_on_risk_decision(...),
simulating exactly what the real event bus would deliver.
"""

from unittest.mock import AsyncMock, patch

import pytest

from backend.app.market_data.option_chain_client import OptionChainLookupError
from backend.app.strategies.manual_trading.engine import ManualTradingEngine, ManualTradingError
from backend.app.strategies.manual_trading.models import ManualOrderRequest


def _row(strike, call_ltp=100.0, put_ltp=90.0, call_key="CE1", put_key="PE1"):
    # instrument_key is a sibling of market_data in the real Upstox
    # response (verified live), not nested inside it.
    return {
        "strike_price": strike,
        "underlying_spot_price": 24500.0,
        "call_options": {"instrument_key": call_key, "market_data": {"ltp": call_ltp}},
        "put_options": {"instrument_key": put_key, "market_data": {"ltp": put_ltp}},
    }


CHAIN = [_row(24400), _row(24500), _row(24600)]

PATCH_TOKEN = "backend.app.strategies.manual_trading.engine.upstox_auth.load_token"
PATCH_FETCH = "backend.app.strategies.manual_trading.engine.fetch_option_chain"
PATCH_PUBLISH = "backend.app.strategies.manual_trading.engine.event_bus.publish"


def _order(**kw):
    d = dict(
        underlying="NIFTY", option_type="CE", strike=24500.0,
        lots=1, stop_loss=50.0, target=150.0, pyramid_lot_size=1,
    )
    d.update(kw)
    return ManualOrderRequest(**d)


async def _confirm_execution(engine, decision_id, status="DRY_RUN"):
    """Simulates the EXECUTION_UPDATE a real ExecutionEngine would publish."""
    await engine._on_execution_update({
        "decision_id": decision_id, "status": status, "mode": "DRY_RUN",
        "order_id": None, "detail": None,
    })


async def _reject_at_risk(engine, decision_id, reason="Rejected."):
    await engine._on_risk_decision({
        "decision_id": decision_id, "approved": False, "reason": reason,
    })


def _entry_decision_id(position) -> str:
    return f"{position.position_id}_ENTRY"


@pytest.mark.asyncio
async def test_place_order_starts_pending_not_open():
    """The core fix this whole file exists to prove: a submitted-but-not
    -yet-confirmed order must never read as OPEN."""
    engine = ManualTradingEngine()

    async def capture(topic, payload):
        pass

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await engine.place_order(_order(lots=2))

    assert position.status == "PENDING"
    assert position.quantity == 2 * 65  # NIFTY lot size
    assert position.entry_price == 100.0  # CE ltp at 24500
    assert position.instrument_token == "CE1"


@pytest.mark.asyncio
async def test_place_order_becomes_open_once_execution_confirms_dry_run():
    engine = ManualTradingEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await engine.place_order(_order(lots=2))
        await _confirm_execution(engine, _entry_decision_id(position), status="DRY_RUN")

    assert engine.positions[position.position_id].status == "OPEN"

    decision = next(p for t, p in published if t == "DECISION_CREATED")
    assert decision["action"] == "TRADE"
    assert decision["transaction_type"] == "BUY"
    assert decision["quantity"] == 130
    assert decision["instrument_token"] == "CE1"


@pytest.mark.asyncio
async def test_place_order_closed_when_execution_rejects():
    engine = ManualTradingEngine()

    async def capture(topic, payload):
        pass

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await engine.place_order(_order())
        await _confirm_execution(engine, _entry_decision_id(position), status="REJECTED")

    final = engine.positions[position.position_id]
    assert final.status == "CLOSED"
    assert final.exit_reason == "ENTRY_REJECTED"
    assert final.closed_at is not None


@pytest.mark.asyncio
async def test_place_order_closed_when_risk_rejects():
    """The exact scenario found live: risk rejects (e.g. outside market
    hours, over a limit) -> position must never read as OPEN."""
    engine = ManualTradingEngine()

    async def capture(topic, payload):
        pass

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await engine.place_order(_order())
        await _reject_at_risk(engine, _entry_decision_id(position), reason="Market not open yet.")

    final = engine.positions[position.position_id]
    assert final.status == "CLOSED"
    assert "Market not open yet" in final.exit_reason
    assert final.exit_reason.startswith("ENTRY_REJECTED")


@pytest.mark.asyncio
async def test_place_order_resolves_atm_strike_when_none_given():
    engine = ManualTradingEngine()

    async def capture(topic, payload):
        pass

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await engine.place_order(_order(strike=None))

    assert position.strike == 24500  # closest to underlying_spot_price=24500.0


@pytest.mark.asyncio
async def test_place_order_rejects_non_positive_lots():
    engine = ManualTradingEngine()
    with pytest.raises(ManualTradingError, match="lots"):
        await engine.place_order(_order(lots=0))


@pytest.mark.asyncio
async def test_place_order_rejects_stop_loss_not_below_target():
    engine = ManualTradingEngine()
    with pytest.raises(ManualTradingError, match="stop_loss"):
        await engine.place_order(_order(stop_loss=150.0, target=100.0))


@pytest.mark.asyncio
async def test_place_order_rejects_unsupported_underlying():
    # FINNIFTY is unsupported by both lot_sizes.LOT_SIZES and
    # symbols.INDEX_INSTRUMENT_KEYS — lot size is checked first, so that's
    # the error the caller sees.
    engine = ManualTradingEngine()
    with pytest.raises(ManualTradingError, match="No known lot size"):
        await engine.place_order(_order(underlying="FINNIFTY"))


@pytest.mark.asyncio
async def test_place_order_without_saved_token_raises():
    engine = ManualTradingEngine()
    with patch(PATCH_TOKEN, return_value=None):
        with pytest.raises(ManualTradingError, match="No saved Upstox token"):
            await engine.place_order(_order())


@pytest.mark.asyncio
async def test_place_order_falls_back_to_next_week_when_current_week_is_empty():
    """Real, observed Upstox behaviour: current_week legitimately returns
    zero rows for some underlyings/times. Confirmed live against this
    exact engine — the first version of this fallback was missing and
    surfaced that as a hard order-placement failure."""
    engine = ManualTradingEngine()

    async def capture(topic, payload):
        pass

    fetch_mock = AsyncMock(side_effect=[OptionChainLookupError("no strikes"), CHAIN])

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=fetch_mock), \
         patch(PATCH_PUBLISH, new=capture):
        position = await engine.place_order(_order())

    assert position.status == "PENDING"
    assert fetch_mock.call_count == 2
    assert fetch_mock.call_args_list[0].args[2] == "current_week"
    assert fetch_mock.call_args_list[1].args[2] == "next_week"


@pytest.mark.asyncio
async def test_place_order_raises_when_both_expiries_fail():
    engine = ManualTradingEngine()
    fetch_mock = AsyncMock(side_effect=[
        OptionChainLookupError("no strikes (current_week)"),
        OptionChainLookupError("no strikes (next_week)"),
    ])

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=fetch_mock):
        with pytest.raises(ManualTradingError, match="tried current_week and next_week"):
            await engine.place_order(_order())


@pytest.mark.asyncio
async def test_place_order_does_not_fall_back_when_next_week_explicitly_requested():
    engine = ManualTradingEngine()
    fetch_mock = AsyncMock(side_effect=OptionChainLookupError("no strikes"))

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=fetch_mock):
        with pytest.raises(ManualTradingError, match="Option chain fetch failed for NIFTY"):
            await engine.place_order(_order(expiry_date="next_week"))

    assert fetch_mock.call_count == 1


async def _open_position(engine, **order_kw):
    """place_order + confirm DRY_RUN -> a real OPEN position, the
    precondition every pyramid/close test needs."""
    position = await engine.place_order(_order(**order_kw))
    await _confirm_execution(engine, _entry_decision_id(position), status="DRY_RUN")
    return engine.positions[position.position_id]


@pytest.mark.asyncio
async def test_add_pyramid_updates_weighted_entry_price_and_quantity_once_confirmed():
    engine = ManualTradingEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await _open_position(engine, lots=1, pyramid_lot_size=1)  # entry @ 100, qty 65
        published.clear()

        pyramid_chain = [_row(24500, call_ltp=120.0, call_key="CE1")]
        with patch(PATCH_FETCH, new=AsyncMock(return_value=pyramid_chain)):
            returned = await engine.add_pyramid(position.position_id)
            # Unconfirmed: quantity/price must NOT have moved yet.
            assert returned.quantity == 65
            assert returned.entry_price == 100.0

        pyramid_decision_id = next(p["decision_id"] for _, p in published if p.get("decision_id", "").startswith(f"{position.position_id}_PYRAMID"))
        await _confirm_execution(engine, pyramid_decision_id, status="DRY_RUN")

    final = engine.positions[position.position_id]
    # (65*100 + 65*120) / 130 = 110
    assert final.entry_price == pytest.approx(110.0)
    assert final.quantity == 130
    assert final.lots == 2

    decision = next(p for t, p in published if t == "DECISION_CREATED")
    assert decision["transaction_type"] == "BUY"
    assert decision["quantity"] == 65


@pytest.mark.asyncio
async def test_add_pyramid_leaves_position_unchanged_when_rejected():
    engine = ManualTradingEngine()

    async def capture(topic, payload):
        pass

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await _open_position(engine, lots=1, pyramid_lot_size=1)

        with patch(PATCH_FETCH, new=AsyncMock(return_value=[_row(24500, call_ltp=120.0, call_key="CE1")])):
            await engine.add_pyramid(position.position_id)

        decision_id = next(iter(engine._pending_pyramids))
        await _reject_at_risk(engine, decision_id, reason="Max positions.")

    final = engine.positions[position.position_id]
    assert final.status == "OPEN"  # unaffected
    assert final.quantity == 65
    assert final.entry_price == 100.0


@pytest.mark.asyncio
async def test_add_pyramid_disabled_when_pyramid_lot_size_zero():
    engine = ManualTradingEngine()

    async def capture(topic, payload):
        pass

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await _open_position(engine, pyramid_lot_size=0)

        with pytest.raises(ManualTradingError, match="pyramiding disabled"):
            await engine.add_pyramid(position.position_id)


@pytest.mark.asyncio
async def test_add_pyramid_unknown_position_raises():
    engine = ManualTradingEngine()
    with pytest.raises(ManualTradingError, match="No position"):
        await engine.add_pyramid("MANUAL_doesnotexist")


@pytest.mark.asyncio
async def test_add_pyramid_rejects_when_position_still_pending():
    engine = ManualTradingEngine()

    async def capture(topic, payload):
        pass

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await engine.place_order(_order())  # never confirmed -> still PENDING

        with pytest.raises(ManualTradingError, match="not OPEN"):
            await engine.add_pyramid(position.position_id)


@pytest.mark.asyncio
async def test_close_position_stays_open_until_execution_confirms():
    engine = ManualTradingEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await _open_position(engine, lots=3)
        published.clear()
        returned = await engine.close_position(position.position_id, reason="MANUAL_CLOSE")

        assert returned.status == "OPEN"  # not yet confirmed
        decision = published[0][1]
        assert decision["transaction_type"] == "SELL"
        assert decision["quantity"] == 3 * 65

        exit_decision_id = decision["decision_id"]
        await _confirm_execution(engine, exit_decision_id, status="DRY_RUN")

    final = engine.positions[position.position_id]
    assert final.status == "CLOSED"
    assert final.exit_reason == "MANUAL_CLOSE"
    assert final.closed_at is not None


@pytest.mark.asyncio
async def test_close_position_stays_open_when_execution_rejects_exit():
    engine = ManualTradingEngine()

    async def capture(topic, payload):
        pass

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await _open_position(engine, lots=1)
        await engine.close_position(position.position_id)

        exit_decision_id = next(iter(engine._pending_exits))
        await _confirm_execution(engine, exit_decision_id, status="ERROR")

    final = engine.positions[position.position_id]
    assert final.status == "OPEN"
    assert final.exit_reason is None


@pytest.mark.asyncio
async def test_close_position_already_closed_raises():
    engine = ManualTradingEngine()

    async def capture(topic, payload):
        pass

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await _open_position(engine)
        await engine.close_position(position.position_id)
        await _confirm_execution(engine, next(iter(engine._pending_exits)), status="DRY_RUN")

        with pytest.raises(ManualTradingError, match="not OPEN"):
            await engine.close_position(position.position_id)


@pytest.mark.asyncio
async def test_monitor_loop_auto_closes_on_stop_loss_hit():
    engine = ManualTradingEngine()

    async def capture(topic, payload):
        if payload.get("decision_id", "").startswith("MANUAL_") and "_EXIT_" in payload.get("decision_id", ""):
            await engine._on_execution_update({
                "decision_id": payload["decision_id"], "status": "DRY_RUN",
            })

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await _open_position(engine, stop_loss=50.0, target=150.0)

        crashed_chain = [_row(24500, call_ltp=40.0, call_key="CE1")]  # below stop_loss
        with patch(PATCH_FETCH, new=AsyncMock(return_value=crashed_chain)), \
             patch(PATCH_TOKEN, return_value="fake-token"):
            await engine._check_positions([position], "fake-token")

    assert engine.positions[position.position_id].status == "CLOSED"
    assert engine.positions[position.position_id].exit_reason == "STOP_LOSS_HIT"


@pytest.mark.asyncio
async def test_monitor_loop_auto_closes_on_target_hit():
    engine = ManualTradingEngine()

    async def capture(topic, payload):
        if "_EXIT_" in payload.get("decision_id", ""):
            await engine._on_execution_update({"decision_id": payload["decision_id"], "status": "DRY_RUN"})

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await _open_position(engine, stop_loss=50.0, target=150.0)

        rallied_chain = [_row(24500, call_ltp=160.0, call_key="CE1")]  # above target
        with patch(PATCH_FETCH, new=AsyncMock(return_value=rallied_chain)):
            await engine._check_positions([position], "fake-token")

    assert engine.positions[position.position_id].status == "CLOSED"
    assert engine.positions[position.position_id].exit_reason == "TARGET_HIT"


@pytest.mark.asyncio
async def test_monitor_loop_leaves_position_open_within_range():
    engine = ManualTradingEngine()

    async def capture(topic, payload):
        pass

    with patch(PATCH_TOKEN, return_value="fake-token"), \
         patch(PATCH_FETCH, new=AsyncMock(return_value=CHAIN)), \
         patch(PATCH_PUBLISH, new=capture):
        position = await _open_position(engine, stop_loss=50.0, target=150.0)

        flat_chain = [_row(24500, call_ltp=105.0, call_key="CE1")]
        with patch(PATCH_FETCH, new=AsyncMock(return_value=flat_chain)):
            await engine._check_positions([position], "fake-token")

    assert engine.positions[position.position_id].status == "OPEN"
    assert engine.positions[position.position_id].last_ltp == 105.0
