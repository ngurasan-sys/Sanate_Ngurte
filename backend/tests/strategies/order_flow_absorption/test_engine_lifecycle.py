"""Covers two gaps found after the initial OFAO build: (1) DRY_RUN status
updates must advance the state machine exactly like SUBMITTED does, since
DRY_RUN is the codebase's default execution mode and setups must not get
stuck forever whenever nobody has armed LIVE; (2) a stop/target hit must
publish a real SELL DECISION_CREATED through the existing execution
pipeline, not just quietly forget the position internally.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.strategies.order_flow_absorption.config import OFAOConfig
from backend.app.strategies.order_flow_absorption.engine import OFAOEngine
from backend.app.strategies.order_flow_absorption.models import SetupDirection, SetupState, TradeIntent

BASE = datetime(2024, 10, 1, 6, 0, tzinfo=timezone.utc)
INSTRUMENT = "NIFTY FUT"


def _resolved_intent(**overrides):
    fields = dict(
        setup_id="NIFTY_2024-10-01_060000_BULL_001", timestamp=BASE, underlying="NIFTY",
        direction="BUY", option_type="CE", strike=25000, expiry="UNRESOLVED", quantity=75,
        underlying_trigger=86.0, underlying_stop=85.0, underlying_target=88.0, risk_reward=2.0,
        score=11, confidence="A+", reason="test", location="test", absorption_strength=90.0,
        imbalance_ratio_pct=300.0, option_instrument_token="NSE_FO|NIFTY25000CE",
    )
    fields.update(overrides)
    return TradeIntent(**fields)


@pytest.fixture
def engine():
    return OFAOEngine(config=OFAOConfig(enabled=True))


def _put_in_order_submitted(engine, intent):
    sm = engine.state_machine
    sm.transition(INSTRUMENT, SetupState.LOCATION_REACHED, now=BASE, direction=SetupDirection.BULL, location_price=86.0)
    ctx = sm.get(INSTRUMENT)
    intent = intent.model_copy(update={"setup_id": ctx.setup_id})
    sm.transition(INSTRUMENT, SetupState.ABSORPTION_DETECTED, now=BASE, absorption_strength=90.0, invalidation_price=85.0)
    sm.transition(INSTRUMENT, SetupState.WAITING_FOR_DOMINANCE, now=BASE)
    sm.transition(INSTRUMENT, SetupState.DOMINANCE_CONFIRMED, now=BASE)
    sm.transition(INSTRUMENT, SetupState.SIGNAL_READY, now=BASE, trade_intent=intent)
    sm.transition(INSTRUMENT, SetupState.ORDER_SUBMITTED, now=BASE, trade_intent=intent)
    return sm.get(INSTRUMENT)


class TestDryRunConfirmsEntry:
    @pytest.mark.asyncio
    async def test_dry_run_status_advances_to_position_active(self, engine):
        ctx = _put_in_order_submitted(engine, _resolved_intent())
        await engine._on_execution_update({"decision_id": f"OFAO_{ctx.setup_id}", "status": "DRY_RUN"})
        assert engine.state_machine.get(INSTRUMENT).state == SetupState.POSITION_ACTIVE

    @pytest.mark.asyncio
    async def test_submitted_status_still_advances_to_position_active(self, engine):
        ctx = _put_in_order_submitted(engine, _resolved_intent())
        await engine._on_execution_update({"decision_id": f"OFAO_{ctx.setup_id}", "status": "SUBMITTED"})
        assert engine.state_machine.get(INSTRUMENT).state == SetupState.POSITION_ACTIVE

    @pytest.mark.asyncio
    async def test_rejected_status_cancels_and_resets(self, engine):
        ctx = _put_in_order_submitted(engine, _resolved_intent())
        await engine._on_execution_update({"decision_id": f"OFAO_{ctx.setup_id}", "status": "REJECTED", "detail": "no funds"})
        assert engine.state_machine.get(INSTRUMENT).state == SetupState.NO_SETUP


class TestPositionExitPublishesSell:
    @pytest.mark.asyncio
    async def test_stop_hit_publishes_sell_decision(self, engine):
        ctx = _put_in_order_submitted(engine, _resolved_intent())
        await engine._on_execution_update({"decision_id": f"OFAO_{ctx.setup_id}", "status": "DRY_RUN"})
        ctx = engine.state_machine.get(INSTRUMENT)
        assert ctx.state == SetupState.POSITION_ACTIVE

        published = []

        async def _fake_publish(channel, payload):
            published.append((channel, payload))

        losing_candle = type("C", (), {"close": 84.5})()
        with patch("backend.app.strategies.order_flow_absorption.engine.event_bus.publish", side_effect=_fake_publish):
            await engine._monitor_position(INSTRUMENT, ctx, [losing_candle], BASE)

        assert len(published) == 1
        channel, payload = published[0]
        assert channel == "DECISION_CREATED"
        assert payload["source"] == "OFAO"
        assert payload["transaction_type"] == "SELL"
        assert payload["quantity"] == 75
        assert payload["instrument_token"] == "NSE_FO|NIFTY25000CE"
        # Position stays POSITION_ACTIVE until the exit is confirmed —
        # it is not forgotten the instant stop/target is observed.
        assert engine.state_machine.get(INSTRUMENT).state == SetupState.POSITION_ACTIVE
        assert len(engine._pending_exits) == 1

    @pytest.mark.asyncio
    async def test_repeated_evaluate_cycles_do_not_duplicate_exit_order(self, engine):
        ctx = _put_in_order_submitted(engine, _resolved_intent())
        await engine._on_execution_update({"decision_id": f"OFAO_{ctx.setup_id}", "status": "DRY_RUN"})
        ctx = engine.state_machine.get(INSTRUMENT)

        published = []

        async def _fake_publish(channel, payload):
            published.append((channel, payload))

        losing_candle = type("C", (), {"close": 84.5})()
        with patch("backend.app.strategies.order_flow_absorption.engine.event_bus.publish", side_effect=_fake_publish):
            await engine._monitor_position(INSTRUMENT, ctx, [losing_candle], BASE)
            await engine._monitor_position(INSTRUMENT, ctx, [losing_candle], BASE)
            await engine._monitor_position(INSTRUMENT, ctx, [losing_candle], BASE)

        assert len(published) == 1

    @pytest.mark.asyncio
    async def test_exit_confirmation_finalizes_exited_and_resets(self, engine):
        ctx = _put_in_order_submitted(engine, _resolved_intent())
        await engine._on_execution_update({"decision_id": f"OFAO_{ctx.setup_id}", "status": "DRY_RUN"})
        ctx = engine.state_machine.get(INSTRUMENT)

        published = []

        async def _fake_publish(channel, payload):
            published.append((channel, payload))

        losing_candle = type("C", (), {"close": 84.5})()
        with patch("backend.app.strategies.order_flow_absorption.engine.event_bus.publish", side_effect=_fake_publish):
            await engine._monitor_position(INSTRUMENT, ctx, [losing_candle], BASE)

        exit_decision_id = published[0][1]["decision_id"]
        await engine._on_execution_update({"decision_id": exit_decision_id, "status": "DRY_RUN"})

        assert engine.state_machine.get(INSTRUMENT).state == SetupState.NO_SETUP
        assert exit_decision_id not in engine._pending_exits

    @pytest.mark.asyncio
    async def test_target_hit_on_position_active_transitions_to_target_1_without_closing(self, engine):
        ctx = _put_in_order_submitted(engine, _resolved_intent())
        await engine._on_execution_update({"decision_id": f"OFAO_{ctx.setup_id}", "status": "DRY_RUN"})
        ctx = engine.state_machine.get(INSTRUMENT)

        winning_candle = type("C", (), {"close": 89.0})()
        with patch("backend.app.strategies.order_flow_absorption.engine.event_bus.publish", new=AsyncMock()) as mock_publish:
            await engine._monitor_position(INSTRUMENT, ctx, [winning_candle], BASE)
            mock_publish.assert_not_called()

        assert engine.state_machine.get(INSTRUMENT).state == SetupState.TARGET_1
