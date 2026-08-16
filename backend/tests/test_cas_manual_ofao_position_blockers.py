from datetime import datetime

from backend.app.strategies.cas_dislocation.engine import CASDislocationEngine
from backend.app.strategies.cas_dislocation.models import CASPosition
from backend.app.strategies.manual_trading.engine import ManualTradingEngine
from backend.app.strategies.manual_trading.models import ManualPosition
from backend.app.strategies.order_flow_absorption.engine import OFAOEngine
from backend.app.strategies.order_flow_absorption.models import SetupDirection, SetupState


def test_cas_blocker_none_when_no_positions():
    engine = CASDislocationEngine()
    assert engine.get_open_position_blocker() is None


def test_cas_blocker_reports_open_positions():
    engine = CASDislocationEngine()
    engine.positions["p1"] = CASPosition(
        position_id="p1", underlying="NIFTY", strike=25000, option_type="CE",
        instrument_token="NSE_FO|1", lots=1, quantity=75, entry_price=100.0,
        max_hold_seconds=90, status="OPEN", created_at=datetime.now(),
    )
    blocker = engine.get_open_position_blocker()
    assert blocker is not None
    assert "1" in blocker


def test_manual_trading_blocker_none_when_no_positions():
    engine = ManualTradingEngine()
    assert engine.get_open_position_blocker() is None


def test_manual_trading_blocker_reports_open_positions():
    engine = ManualTradingEngine()
    engine.positions["p1"] = ManualPosition(
        position_id="p1", underlying="NIFTY", strike=25000, option_type="CE",
        instrument_token="NSE_FO|1", expiry_date="current_week", lots=1, quantity=75,
        entry_price=100.0, stop_loss=80.0, target=150.0, pyramid_lot_size=0,
        status="OPEN", created_at=datetime.now(),
    )
    blocker = engine.get_open_position_blocker()
    assert blocker is not None


def test_ofao_blocker_none_when_no_active_setup():
    engine = OFAOEngine()
    assert engine.get_open_position_blocker() is None


def test_ofao_blocker_reports_active_setup():
    engine = OFAOEngine()
    engine.state_machine.transition(
        "NIFTY FUT", SetupState.LOCATION_REACHED, direction=SetupDirection.BULL, location_price=100.0,
    )
    blocker = engine.get_open_position_blocker()
    assert blocker is not None
    assert "NIFTY FUT" in blocker


def test_ofao_blocker_goes_through_the_state_machines_public_predicate():
    """get_open_position_blocker() must read active_setups() rather than
    re-implementing the predicate over state_machine._contexts."""
    engine = OFAOEngine()
    engine.state_machine.transition(
        "NIFTY FUT", SetupState.LOCATION_REACHED, direction=SetupDirection.BULL, location_price=100.0,
    )
    assert engine.state_machine.active_setups() == ["NIFTY FUT"]

    # Once terminal, the setup is no longer a blocker.
    engine.state_machine.transition("NIFTY FUT", SetupState.INVALIDATED)
    assert engine.state_machine.active_setups() == []
    assert engine.get_open_position_blocker() is None
