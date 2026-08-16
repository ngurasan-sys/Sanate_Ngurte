import httpx
import pytest

from backend.app.execution import order_gateway as gw_module
from backend.app.execution.order_gateway import (
    ExecutionMode,
    OrderGateway,
    OrderRequest,
    resolve_mode,
)
from backend.app.execution.runtime_state import execution_runtime_state
from backend.app.execution import upstox_adapter as ua_module

_RealAsyncClient = httpx.AsyncClient


@pytest.fixture(autouse=True)
def _reset_runtime_arm_state():
    # The runtime arm switch is a process-wide singleton — leaking an
    # armed state from one test into the next would let LIVE mode
    # activate without either test actually asking for it.
    execution_runtime_state.disarm()
    yield
    execution_runtime_state.disarm()


from backend.app.core import active_broker as ab_module
from backend.app.execution.upstox_adapter import upstox_execution_adapter


class _AlwaysTokenAuth:
    def load_token(self):
        return "test-token"  # SANDBOX/LIVE tests set their own real token expectation via monkeypatch


class _StubProvider:
    async def connect_feed(self):
        pass

    async def disconnect_feed(self):
        pass


@pytest.fixture(autouse=True)
def _activate_upstox_for_tests(monkeypatch, tmp_path):
    """order_gateway.place_order only needs an active execution adapter,
    not a running feed — set the registry's state directly rather than
    going through the full async set_active_broker() (which would also
    try to connect a feed and publish an event, neither of which matters
    here, and calling an async method from a sync autouse fixture would
    fight pytest-asyncio's own event loop management).
    """
    monkeypatch.setattr(ab_module, "STATE_PATH", tmp_path / "active_broker.json")
    registry = ab_module.ActiveBrokerRegistry()
    registry.register_broker(
        "upstox", provider=_StubProvider(), execution_adapter=upstox_execution_adapter,
        auth_module=_AlwaysTokenAuth(),
    )
    registry._active_broker_id = "upstox"
    monkeypatch.setattr(ab_module, "active_broker", registry)
    monkeypatch.setattr(gw_module, "active_broker", registry)
    yield


def _mock_client_factory(transport):
    return lambda *a, **kw: _RealAsyncClient(transport=transport)


def _req(**kw):
    defaults = dict(
        instrument_token="NSE_FO|12345", transaction_type="BUY", quantity=50,
    )
    defaults.update(kw)
    return OrderRequest(**defaults)


# --------------------------- mode resolution ---------------------------

def test_default_mode_is_dry_run(monkeypatch):
    monkeypatch.delenv("EXECUTION_MODE", raising=False)
    assert resolve_mode() is ExecutionMode.DRY_RUN


def test_unrecognised_mode_falls_back_to_dry_run(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "YOLO")
    assert resolve_mode() is ExecutionMode.DRY_RUN


def test_live_mode_requires_second_confirmation_switch(monkeypatch):
    # A single env var must NOT be able to arm real-money trading.
    monkeypatch.setenv("EXECUTION_MODE", "LIVE")
    monkeypatch.delenv("LIVE_TRADING_CONFIRMED", raising=False)
    assert resolve_mode() is ExecutionMode.DRY_RUN


def test_live_mode_requires_confirmation_to_be_exactly_yes(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "LIVE")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "true")
    assert resolve_mode() is ExecutionMode.DRY_RUN


def test_live_mode_armed_only_with_both_switches(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "LIVE")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "YES")
    assert resolve_mode() is ExecutionMode.LIVE


def test_live_mode_armed_via_runtime_switch_alone(monkeypatch):
    # The runtime arm switch (toggled from the frontend) is an
    # independent alternative to the env-var confirmation — either one
    # satisfies the second switch, but EXECUTION_MODE=LIVE is
    # still required as the first.
    monkeypatch.setenv("EXECUTION_MODE", "LIVE")
    monkeypatch.delenv("LIVE_TRADING_CONFIRMED", raising=False)
    execution_runtime_state.arm(note="test")
    assert resolve_mode() is ExecutionMode.LIVE


def test_runtime_switch_alone_without_live_env_mode_stays_dry_run(monkeypatch):
    monkeypatch.delenv("EXECUTION_MODE", raising=False)
    execution_runtime_state.arm(note="test")
    assert resolve_mode() is ExecutionMode.DRY_RUN


def test_sandbox_mode_needs_no_extra_confirmation(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "SANDBOX")
    assert resolve_mode() is ExecutionMode.SANDBOX


# --------------------------- payload shape ---------------------------

def test_payload_matches_upstox_field_names():
    payload = _req(quantity=75, price=101.5, order_type="LIMIT").to_payload()
    assert payload == {
        "quantity": 75,
        "product": "I",
        "validity": "DAY",
        "price": 101.5,
        "instrument_token": "NSE_FO|12345",
        "order_type": "LIMIT",
        "transaction_type": "BUY",
        "disclosed_quantity": 0,
        "trigger_price": 0.0,
    }


def test_payload_includes_tag_only_when_set():
    assert "tag" not in _req().to_payload()
    assert _req(tag="dec_1").to_payload()["tag"] == "dec_1"


# --------------------------- DRY_RUN ---------------------------

@pytest.mark.asyncio
async def test_dry_run_makes_no_network_call(monkeypatch):
    monkeypatch.delenv("EXECUTION_MODE", raising=False)

    def explode(*a, **kw):
        raise AssertionError("DRY_RUN must never open a network client")

    monkeypatch.setattr(ua_module.httpx, "AsyncClient", explode)

    result = await OrderGateway().place_order(_req())

    assert result.status == "DRY_RUN"
    assert result.order_id is None
    assert result.is_real_submission is False
    assert result.payload["quantity"] == 50


# --------------------------- real submission ---------------------------

@pytest.mark.asyncio
async def test_sandbox_submission_returns_order_id(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "SANDBOX")
    monkeypatch.setenv("UPSTOX_SANDBOX_ACCESS_TOKEN", "sbx-token")

    def handler(request):
        assert "api-sandbox.upstox.com" in str(request.url)
        assert request.headers["Authorization"] == "Bearer sbx-token"
        return httpx.Response(200, json={"status": "success", "data": {"order_id": "ORD123"}})

    monkeypatch.setattr(
        ua_module.httpx, "AsyncClient", _mock_client_factory(httpx.MockTransport(handler))
    )

    result = await OrderGateway().place_order(_req())
    assert result.status == "SUBMITTED"
    assert result.order_id == "ORD123"
    assert result.is_real_submission is True


@pytest.mark.asyncio
async def test_sandbox_without_token_is_rejected_before_network(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "SANDBOX")
    monkeypatch.delenv("UPSTOX_SANDBOX_ACCESS_TOKEN", raising=False)

    def explode(*a, **kw):
        raise AssertionError("must not call the network without a token")

    monkeypatch.setattr(ua_module.httpx, "AsyncClient", explode)

    result = await OrderGateway().place_order(_req())
    assert result.status == "REJECTED"
    assert result.is_real_submission is False


@pytest.mark.asyncio
async def test_live_mode_targets_the_hft_host(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "LIVE")
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "YES")
    monkeypatch.setattr(ua_module.upstox_auth, "load_token", lambda: "live-token")

    def handler(request):
        assert "api-hft.upstox.com" in str(request.url)
        return httpx.Response(200, json={"status": "success", "data": {"order_id": "LIVE1"}})

    monkeypatch.setattr(
        ua_module.httpx, "AsyncClient", _mock_client_factory(httpx.MockTransport(handler))
    )

    result = await OrderGateway().place_order(_req())
    assert result.mode is ExecutionMode.LIVE
    assert result.order_id == "LIVE1"


# --------------------------- failure honesty ---------------------------

@pytest.mark.asyncio
async def test_broker_rejection_is_not_reported_as_submitted(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "SANDBOX")
    monkeypatch.setenv("UPSTOX_SANDBOX_ACCESS_TOKEN", "sbx")

    def handler(request):
        return httpx.Response(400, json={"status": "error", "errors": [{"message": "bad qty"}]})

    monkeypatch.setattr(
        ua_module.httpx, "AsyncClient", _mock_client_factory(httpx.MockTransport(handler))
    )

    result = await OrderGateway().place_order(_req())
    assert result.status == "REJECTED"
    assert result.is_real_submission is False
    assert "bad qty" in result.detail


@pytest.mark.asyncio
async def test_transport_failure_reports_unknown_not_submitted(monkeypatch):
    """A network failure means we genuinely don't know if the broker got
    the order. It must never be reported as submitted."""
    monkeypatch.setenv("EXECUTION_MODE", "SANDBOX")
    monkeypatch.setenv("UPSTOX_SANDBOX_ACCESS_TOKEN", "sbx")

    def handler(request):
        raise httpx.ConnectError("connection reset")

    monkeypatch.setattr(
        ua_module.httpx, "AsyncClient", _mock_client_factory(httpx.MockTransport(handler))
    )

    result = await OrderGateway().place_order(_req())
    assert result.status == "ERROR"
    assert result.is_real_submission is False
    assert "UNKNOWN" in result.detail


@pytest.mark.asyncio
async def test_no_active_broker_is_rejected_before_network(monkeypatch):
    """SANDBOX/LIVE must never silently fall back to some default broker.
    With no execution adapter registered for the active broker, place_order
    must reject cleanly rather than crash or guess a broker."""
    monkeypatch.setenv("EXECUTION_MODE", "SANDBOX")
    monkeypatch.setenv("UPSTOX_SANDBOX_ACCESS_TOKEN", "sbx-token")

    # Override the autouse _activate_upstox_for_tests fixture's registry:
    # a registry with no active broker at all.
    registry = ab_module.ActiveBrokerRegistry()
    registry._active_broker_id = None
    monkeypatch.setattr(gw_module, "active_broker", registry)

    def explode(*a, **kw):
        raise AssertionError("must not call the network with no active broker")

    monkeypatch.setattr(ua_module.httpx, "AsyncClient", explode)

    result = await OrderGateway().place_order(_req())
    assert result.status == "REJECTED"
    assert result.is_real_submission is False
    assert result.order_id is None


@pytest.mark.asyncio
async def test_200_without_order_id_is_not_submitted(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "SANDBOX")
    monkeypatch.setenv("UPSTOX_SANDBOX_ACCESS_TOKEN", "sbx")

    def handler(request):
        return httpx.Response(200, json={"status": "success", "data": {}})

    monkeypatch.setattr(
        ua_module.httpx, "AsyncClient", _mock_client_factory(httpx.MockTransport(handler))
    )

    result = await OrderGateway().place_order(_req())
    assert result.status == "ERROR"
    assert result.is_real_submission is False
