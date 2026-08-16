"""Engine tests for the CAS Dislocation Engine — drives _tick() through a
realistic PRE_CAS -> CAS_FREEZE -> DISLOCATION timeline with mocked
network calls, same "patch the network boundary, inspect real behaviour"
style as test_manual_trading_engine.py.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytz

from backend.app.core import active_broker as ab_module
from backend.app.strategies.cas_dislocation import engine as engine_module
from backend.app.strategies.cas_dislocation.config_state import cas_config_state
from backend.app.strategies.cas_dislocation.engine import CASDislocationEngine

IST = pytz.timezone("Asia/Kolkata")

PATCH_DATETIME = "backend.app.strategies.cas_dislocation.engine.datetime"
PATCH_EXPIRY = "backend.app.strategies.cas_dislocation.engine.expiry_calendar.is_today_expiry_day"
PATCH_FUTURES_KEY = "backend.app.strategies.cas_dislocation.engine.futures_instrument_cache.get"
PATCH_PUBLISH = "backend.app.strategies.cas_dislocation.engine.event_bus.publish"


class FakeQuote:
    def __init__(self, last_price):
        self.last_price = last_price


class _FakeAuth:
    def load_token(self):
        return "fake-token"


class _FakeProvider:
    def __init__(self, chain, future_price):
        self._chain = chain
        self._future_price = future_price

    def instrument_key_for_index(self, underlying):
        return "NSE_INDEX|Nifty 50"

    async def fetch_option_chain(self, index_key, token, expiry_date="current_week"):
        return self._chain

    async def fetch_quote(self, instrument_key, token):
        return FakeQuote(self._future_price)


def _row(strike, spot, expiry, ce_ltp, ce_bid, ce_ask, ce_iv, pe_ltp, pe_bid, pe_ask, pe_iv, ce_vol=1000, pe_vol=1000):
    return {
        "strike_price": strike,
        "underlying_spot_price": spot,
        "expiry": expiry,
        "call_options": {
            "instrument_key": "NSE_FO|CE1",
            "market_data": {"ltp": ce_ltp, "bid_price": ce_bid, "ask_price": ce_ask, "volume": ce_vol},
            "option_greeks": {"iv": ce_iv},
        },
        "put_options": {
            "instrument_key": "NSE_FO|PE1",
            "market_data": {"ltp": pe_ltp, "bid_price": pe_bid, "ask_price": pe_ask, "volume": pe_vol},
            "option_greeks": {"iv": pe_iv},
        },
    }


def _mock_now(t: datetime):
    mock_dt = AsyncMock()
    mock_dt.now = lambda tz=None: t
    return mock_dt


@pytest.fixture(autouse=True)
def _reset_config():
    cas_config_state.configure(underlying="NIFTY", lots=1)
    yield
    cas_config_state.configure(underlying="NIFTY", lots=1)


async def _tick_at(engine, when: datetime, chain, future_price, publish_capture, monkeypatch):
    registry = ab_module.ActiveBrokerRegistry()
    registry.register_broker(
        "upstox", provider=_FakeProvider(chain, future_price), auth_module=_FakeAuth(),
    )
    registry._active_broker_id = "upstox"
    monkeypatch.setattr(engine_module, "active_broker", registry)

    with patch(PATCH_DATETIME, new=_mock_now(when)), \
         patch(PATCH_EXPIRY, new=AsyncMock(return_value=True)), \
         patch(PATCH_FUTURES_KEY, new=AsyncMock(return_value="NSE_FO|FUT1")), \
         patch(PATCH_PUBLISH, new=publish_capture):
        await engine._tick()


NORMAL_CHAIN = [_row(24800, 24800.0, "2026-08-18", ce_ltp=20.0, ce_bid=19.5, ce_ask=20.5, ce_iv=15.0, pe_ltp=25.0, pe_bid=24.5, pe_ask=25.5, pe_iv=15.0)]


@pytest.mark.asyncio
async def test_tick_outside_watch_window_is_inactive(monkeypatch):
    engine = CASDislocationEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    await _tick_at(engine, datetime(2026, 8, 18, 12, 0, 0, tzinfo=IST), NORMAL_CHAIN, 24800.0, capture, monkeypatch)

    assert engine.latest_reading.state == "INACTIVE"


@pytest.mark.asyncio
async def test_tick_pre_cas_tracks_baseline_volume(monkeypatch):
    engine = CASDislocationEngine()

    async def capture(topic, payload):
        pass

    chain1 = [_row(24800, 24800.0, "2026-08-18", 20.0, 19.5, 20.5, 15.0, 25.0, 24.5, 25.5, 15.0, ce_vol=1000, pe_vol=1000)]
    chain2 = [_row(24800, 24800.0, "2026-08-18", 20.0, 19.5, 20.5, 15.0, 25.0, 24.5, 25.5, 15.0, ce_vol=1100, pe_vol=1050)]

    await _tick_at(engine, datetime(2026, 8, 18, 15, 5, 0, tzinfo=IST), chain1, 24800.0, capture, monkeypatch)
    assert engine.latest_reading.state == "PRE_CAS"

    await _tick_at(engine, datetime(2026, 8, 18, 15, 6, 0, tzinfo=IST), chain2, 24800.0, capture, monkeypatch)
    assert engine.latest_reading.state == "PRE_CAS"
    assert list(engine._volume_history_pre_cas) == [150]  # (1100-1000)+(1050-1000)


@pytest.mark.asyncio
async def test_tick_at_freeze_captures_snapshot(monkeypatch):
    engine = CASDislocationEngine()

    async def capture(topic, payload):
        pass

    await _tick_at(engine, datetime(2026, 8, 18, 15, 15, 0, tzinfo=IST), NORMAL_CHAIN, 24800.0, capture, monkeypatch)

    assert engine.latest_reading.state == "CAS_FREEZE"
    assert engine.snapshot is not None
    assert engine.snapshot.frozen_spot == 24800.0
    assert engine.snapshot.atm_strike == 24800.0
    assert engine.snapshot.baseline_ce_iv == pytest.approx(0.15)
    assert engine.snapshot.baseline_pe_iv == pytest.approx(0.15)


@pytest.mark.asyncio
async def test_tick_dislocation_detects_underpriced_ce_and_signals(monkeypatch):
    engine = CASDislocationEngine()
    cas_config_state.configure(underlying="NIFTY", lots=1, min_score_to_alert=1, min_score_to_execute=1)

    async def capture(topic, payload):
        pass

    # Freeze at 15:15 with spot=future=24800.
    await _tick_at(engine, datetime(2026, 8, 18, 15, 15, 0, tzinfo=IST), NORMAL_CHAIN, 24800.0, capture, monkeypatch)
    assert engine.latest_reading.state == "CAS_FREEZE"

    # Futures rip 70 points higher; CE ask (20.5) is still cheap relative
    # to what it should be worth now, PE ask barely moved -> CE underpriced.
    moved_chain = [_row(24800, 24800.0, "2026-08-18", ce_ltp=21.0, ce_bid=20.0, ce_ask=21.0,
                         ce_iv=15.0, pe_ltp=24.0, pe_bid=23.0, pe_ask=24.0, pe_iv=15.0, ce_vol=1500, pe_vol=1200)]
    await _tick_at(engine, datetime(2026, 8, 18, 15, 15, 5, tzinfo=IST), moved_chain, 24870.0, capture, monkeypatch)

    reading = engine.latest_reading
    assert reading.future_displacement == pytest.approx(70.0)
    assert reading.ce_theoretical > reading.ce_ask  # underpriced
    assert reading.signal in ("BUY_CE", "NONE")  # exact signal depends on dislocation magnitude
    assert reading.state in ("DISLOCATION", "SIGNAL")


@pytest.mark.asyncio
async def test_tick_detects_volatility_shock_blocks_signal(monkeypatch):
    engine = CASDislocationEngine()

    async def capture(topic, payload):
        pass

    baseline_chain = [_row(24800, 24800.0, "2026-08-18", ce_ltp=3.0, ce_bid=2.5, ce_ask=3.0,
                            ce_iv=15.0, pe_ltp=3.0, pe_bid=2.5, pe_ask=3.0, pe_iv=15.0)]
    await _tick_at(engine, datetime(2026, 8, 18, 15, 15, 0, tzinfo=IST), baseline_chain, 24800.0, capture, monkeypatch)
    assert engine.latest_reading.state == "CAS_FREEZE"

    # Both CE and PE LTP spike from 3 -> 80 together — the exact shock
    # signature this engine exists to refuse to trade.
    shock_chain = [_row(24800, 24800.0, "2026-08-18", ce_ltp=80.0, ce_bid=75.0, ce_ask=82.0,
                         ce_iv=15.0, pe_ltp=80.0, pe_bid=75.0, pe_ask=82.0, pe_iv=15.0)]
    await _tick_at(engine, datetime(2026, 8, 18, 15, 15, 5, tzinfo=IST), shock_chain, 24800.0, capture, monkeypatch)

    reading = engine.latest_reading
    assert reading.state == "VOLATILITY_SHOCK"
    assert reading.signal == "NONE"


@pytest.mark.asyncio
async def test_tick_past_dislocation_end_is_inactive(monkeypatch):
    engine = CASDislocationEngine()

    async def capture(topic, payload):
        pass

    await _tick_at(engine, datetime(2026, 8, 18, 15, 18, 0, tzinfo=IST), NORMAL_CHAIN, 24800.0, capture, monkeypatch)
    assert engine.latest_reading.state == "INACTIVE"
    assert "15:17" in engine.latest_reading.reason


# --------------------------- position lifecycle ---------------------------

async def _confirm_execution(engine, decision_id, status="DRY_RUN"):
    await engine._on_execution_update({"decision_id": decision_id, "status": status})


async def _reject_at_risk(engine, decision_id, reason="Rejected."):
    await engine._on_risk_decision({"decision_id": decision_id, "approved": False, "reason": reason})


@pytest.mark.asyncio
async def test_execute_signal_creates_pending_then_open_position():
    engine = CASDislocationEngine()
    cas_config_state.configure(underlying="NIFTY", lots=2)
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    from backend.app.strategies.cas_dislocation.models import CASReading

    row = NORMAL_CHAIN[0]
    reading = CASReading(timestamp=datetime.now(), state="SIGNAL", signal="BUY_CE", score=90)

    with patch(PATCH_PUBLISH, new=capture):
        await engine._execute_signal(reading, row, cas_config_state.get())

    assert len(engine.positions) == 1
    position = next(iter(engine.positions.values()))
    assert position.status == "PENDING"
    assert position.quantity == 2 * 65  # NIFTY lot size
    assert position.instrument_token == "NSE_FO|CE1"

    decision = next(p for t, p in published if t == "DECISION_CREATED")
    assert decision["source"] == "CAS_DISLOCATION"
    assert decision["transaction_type"] == "BUY"
    assert decision["quantity"] == 130

    decision_id = decision["decision_id"]
    await _confirm_execution(engine, decision_id, status="DRY_RUN")
    assert engine.positions[position.position_id].status == "OPEN"
    assert engine.positions[position.position_id].opened_at is not None


@pytest.mark.asyncio
async def test_execute_signal_closed_when_risk_rejects():
    engine = CASDislocationEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    from backend.app.strategies.cas_dislocation.models import CASReading
    reading = CASReading(timestamp=datetime.now(), state="SIGNAL", signal="BUY_CE", score=90)

    with patch(PATCH_PUBLISH, new=capture):
        await engine._execute_signal(reading, NORMAL_CHAIN[0], cas_config_state.get())

    position = next(iter(engine.positions.values()))
    decision_id = f"{position.position_id}_ENTRY"
    await _reject_at_risk(engine, decision_id, reason="Market not open yet.")

    final = engine.positions[position.position_id]
    assert final.status == "CLOSED"
    assert "Market not open yet" in final.exit_reason


@pytest.mark.asyncio
async def test_has_active_position_prevents_duplicate_entries():
    engine = CASDislocationEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    from backend.app.strategies.cas_dislocation.models import CASReading
    reading = CASReading(timestamp=datetime.now(), state="SIGNAL", signal="BUY_CE", score=90)

    with patch(PATCH_PUBLISH, new=capture):
        await engine._execute_signal(reading, NORMAL_CHAIN[0], cas_config_state.get())

    assert engine._has_active_position() is True  # PENDING counts as active
    assert len(engine.positions) == 1


@pytest.mark.asyncio
async def test_auto_exit_on_max_hold_elapsed():
    engine = CASDislocationEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    from backend.app.strategies.cas_dislocation.models import CASPosition

    position = CASPosition(
        position_id="CAS_test1", underlying="NIFTY", option_type="CE", strike=24800.0,
        instrument_token="NSE_FO|CE1", lots=1, quantity=65, entry_price=20.0,
        max_hold_seconds=90, status="OPEN",
        created_at=datetime(2026, 8, 18, 15, 15, 0, tzinfo=IST),
        opened_at=datetime(2026, 8, 18, 15, 15, 0, tzinfo=IST),
    )
    engine.positions[position.position_id] = position

    with patch(PATCH_PUBLISH, new=capture):
        # 100s later — past the 90s max hold.
        await engine._check_position_exits(datetime(2026, 8, 18, 15, 16, 40, tzinfo=IST))

    exit_decision = next(p for t, p in published if t == "DECISION_CREATED")
    assert exit_decision["transaction_type"] == "SELL"
    assert "MAX_HOLD_ELAPSED" in exit_decision["reasoning"]
    assert position.status == "OPEN"  # still OPEN until execution confirms

    decision_id = exit_decision["decision_id"]
    await _confirm_execution(engine, decision_id, status="DRY_RUN")
    assert engine.positions[position.position_id].status == "CLOSED"


@pytest.mark.asyncio
async def test_no_exit_before_max_hold_elapsed():
    engine = CASDislocationEngine()
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    from backend.app.strategies.cas_dislocation.models import CASPosition

    position = CASPosition(
        position_id="CAS_test2", underlying="NIFTY", option_type="CE", strike=24800.0,
        instrument_token="NSE_FO|CE1", lots=1, quantity=65, entry_price=20.0,
        max_hold_seconds=90, status="OPEN",
        created_at=datetime(2026, 8, 18, 15, 15, 0, tzinfo=IST),
        opened_at=datetime(2026, 8, 18, 15, 15, 0, tzinfo=IST),
    )
    engine.positions[position.position_id] = position

    with patch(PATCH_PUBLISH, new=capture):
        await engine._check_position_exits(datetime(2026, 8, 18, 15, 16, 0, tzinfo=IST))  # only 60s elapsed

    assert published == []
    assert position.status == "OPEN"


# --------------------------- manual execute-current-signal ---------------------------

@pytest.mark.asyncio
async def test_execute_current_signal_no_reading_raises():
    from backend.app.strategies.cas_dislocation.engine import CASExecutionError

    engine = CASDislocationEngine()
    with pytest.raises(CASExecutionError, match="No active signal"):
        await engine.execute_current_signal()


@pytest.mark.asyncio
async def test_execute_current_signal_none_signal_raises():
    from backend.app.strategies.cas_dislocation.engine import CASExecutionError
    from backend.app.strategies.cas_dislocation.models import CASReading

    engine = CASDislocationEngine()
    engine.latest_reading = CASReading(timestamp=datetime.now(), state="DISLOCATION", signal="NONE", score=10)
    with pytest.raises(CASExecutionError, match="No active signal"):
        await engine.execute_current_signal()


@pytest.mark.asyncio
async def test_execute_current_signal_blocked_during_shock():
    from backend.app.strategies.cas_dislocation.engine import CASExecutionError
    from backend.app.strategies.cas_dislocation.models import CASReading

    engine = CASDislocationEngine()
    engine.latest_reading = CASReading(timestamp=datetime.now(), state="VOLATILITY_SHOCK", signal="BUY_CE", score=90)
    engine._latest_row = NORMAL_CHAIN[0]
    with pytest.raises(CASExecutionError, match="volatility shock"):
        await engine.execute_current_signal()


@pytest.mark.asyncio
async def test_execute_current_signal_success_creates_position():
    from backend.app.strategies.cas_dislocation.models import CASReading

    engine = CASDislocationEngine()
    engine.latest_reading = CASReading(timestamp=datetime.now(), state="SIGNAL", signal="BUY_CE", score=90)
    engine._latest_row = NORMAL_CHAIN[0]

    async def capture(topic, payload):
        pass

    with patch(PATCH_PUBLISH, new=capture):
        position = await engine.execute_current_signal()

    assert position.status == "PENDING"
    assert position.option_type == "CE"
    assert position.instrument_token == "NSE_FO|CE1"


@pytest.mark.asyncio
async def test_execute_current_signal_blocked_with_active_position():
    from backend.app.strategies.cas_dislocation.engine import CASExecutionError
    from backend.app.strategies.cas_dislocation.models import CASPosition, CASReading

    engine = CASDislocationEngine()
    engine.latest_reading = CASReading(timestamp=datetime.now(), state="SIGNAL", signal="BUY_CE", score=90)
    engine._latest_row = NORMAL_CHAIN[0]
    engine.positions["existing"] = CASPosition(
        position_id="existing", underlying="NIFTY", option_type="CE", strike=24800.0,
        instrument_token="NSE_FO|CE1", lots=1, quantity=65, entry_price=20.0,
        max_hold_seconds=90, status="OPEN", created_at=datetime.now(),
    )

    with pytest.raises(CASExecutionError, match="already PENDING or OPEN"):
        await engine.execute_current_signal()


# --------------------------- manual abort ---------------------------

@pytest.mark.asyncio
async def test_close_position_manually_success():
    from backend.app.strategies.cas_dislocation.models import CASPosition

    engine = CASDislocationEngine()
    position = CASPosition(
        position_id="CAS_abort1", underlying="NIFTY", option_type="CE", strike=24800.0,
        instrument_token="NSE_FO|CE1", lots=1, quantity=65, entry_price=20.0,
        max_hold_seconds=90, status="OPEN", created_at=datetime.now(IST), opened_at=datetime.now(IST),
    )
    engine.positions[position.position_id] = position
    published = []

    async def capture(topic, payload):
        published.append((topic, payload))

    with patch(PATCH_PUBLISH, new=capture):
        await engine.close_position_manually(position.position_id)

    decision = next(p for t, p in published if t == "DECISION_CREATED")
    assert decision["transaction_type"] == "SELL"
    assert "MANUAL_ABORT" in decision["reasoning"]
    assert position.status == "OPEN"  # not yet confirmed

    await _confirm_execution(engine, decision["decision_id"], status="DRY_RUN")
    assert engine.positions[position.position_id].status == "CLOSED"
    assert engine.positions[position.position_id].exit_reason == "MANUAL_ABORT"


@pytest.mark.asyncio
async def test_close_position_manually_unknown_position_raises():
    from backend.app.strategies.cas_dislocation.engine import CASExecutionError

    engine = CASDislocationEngine()
    with pytest.raises(CASExecutionError, match="No position"):
        await engine.close_position_manually("CAS_missing")


@pytest.mark.asyncio
async def test_close_position_manually_rejects_non_open_position():
    from backend.app.strategies.cas_dislocation.engine import CASExecutionError
    from backend.app.strategies.cas_dislocation.models import CASPosition

    engine = CASDislocationEngine()
    position = CASPosition(
        position_id="CAS_pending1", underlying="NIFTY", option_type="CE", strike=24800.0,
        instrument_token="NSE_FO|CE1", lots=1, quantity=65, entry_price=20.0,
        max_hold_seconds=90, status="PENDING", created_at=datetime.now(IST),
    )
    engine.positions[position.position_id] = position

    with pytest.raises(CASExecutionError, match="not OPEN"):
        await engine.close_position_manually(position.position_id)


@pytest.mark.asyncio
async def test_exit_rejected_stays_open():
    engine = CASDislocationEngine()

    async def capture(topic, payload):
        pass

    from backend.app.strategies.cas_dislocation.models import CASPosition

    position = CASPosition(
        position_id="CAS_test3", underlying="NIFTY", option_type="CE", strike=24800.0,
        instrument_token="NSE_FO|CE1", lots=1, quantity=65, entry_price=20.0,
        max_hold_seconds=90, status="OPEN",
        created_at=datetime(2026, 8, 18, 15, 15, 0, tzinfo=IST),
        opened_at=datetime(2026, 8, 18, 15, 15, 0, tzinfo=IST),
    )
    engine.positions[position.position_id] = position

    with patch(PATCH_PUBLISH, new=capture):
        await engine._check_position_exits(datetime(2026, 8, 18, 15, 16, 40, tzinfo=IST))

    exit_decision_id = next(iter(engine._pending_exits))
    await _reject_at_risk(engine, exit_decision_id, reason="kill switch")

    assert engine.positions[position.position_id].status == "OPEN"
    assert engine.positions[position.position_id].exit_reason is None
