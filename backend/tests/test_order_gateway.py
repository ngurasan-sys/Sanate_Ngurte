import httpx
import pytest

from backend.app.execution import order_gateway as gw_module
from backend.app.execution.order_gateway import (
    ExecutionMode,
    OrderGateway,
    OrderRequest,
    resolve_mode,
)

_RealAsyncClient = httpx.AsyncClient


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
    monkeypatch.delenv("UPSTOX_EXECUTION_MODE", raising=False)
    assert resolve_mode() is ExecutionMode.DRY_RUN


def test_unrecognised_mode_falls_back_to_dry_run(monkeypatch):
    monkeypatch.setenv("UPSTOX_EXECUTION_MODE", "YOLO")
    assert resolve_mode() is ExecutionMode.DRY_RUN


def test_live_mode_requires_second_confirmation_switch(monkeypatch):
    # A single env var must NOT be able to arm real-money trading.
    monkeypatch.setenv("UPSTOX_EXECUTION_MODE", "LIVE")
    monkeypatch.delenv("UPSTOX_LIVE_TRADING_CONFIRMED", raising=False)
    assert resolve_mode() is ExecutionMode.DRY_RUN


def test_live_mode_requires_confirmation_to_be_exactly_yes(monkeypatch):
    monkeypatch.setenv("UPSTOX_EXECUTION_MODE", "LIVE")
    monkeypatch.setenv("UPSTOX_LIVE_TRADING_CONFIRMED", "true")
    assert resolve_mode() is ExecutionMode.DRY_RUN


def test_live_mode_armed_only_with_both_switches(monkeypatch):
    monkeypatch.setenv("UPSTOX_EXECUTION_MODE", "LIVE")
    monkeypatch.setenv("UPSTOX_LIVE_TRADING_CONFIRMED", "YES")
    assert resolve_mode() is ExecutionMode.LIVE


def test_sandbox_mode_needs_no_extra_confirmation(monkeypatch):
    monkeypatch.setenv("UPSTOX_EXECUTION_MODE", "SANDBOX")
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
    monkeypatch.delenv("UPSTOX_EXECUTION_MODE", raising=False)

    def explode(*a, **kw):
        raise AssertionError("DRY_RUN must never open a network client")

    monkeypatch.setattr(gw_module.httpx, "AsyncClient", explode)

    result = await OrderGateway().place_order(_req())

    assert result.status == "DRY_RUN"
    assert result.order_id is None
    assert result.is_real_submission is False
    assert result.payload["quantity"] == 50


# --------------------------- real submission ---------------------------

@pytest.mark.asyncio
async def test_sandbox_submission_returns_order_id(monkeypatch):
    monkeypatch.setenv("UPSTOX_EXECUTION_MODE", "SANDBOX")
    monkeypatch.setenv("UPSTOX_SANDBOX_ACCESS_TOKEN", "sbx-token")

    def handler(request):
        assert "api-sandbox.upstox.com" in str(request.url)
        assert request.headers["Authorization"] == "Bearer sbx-token"
        return httpx.Response(200, json={"status": "success", "data": {"order_id": "ORD123"}})

    monkeypatch.setattr(
        gw_module.httpx, "AsyncClient", _mock_client_factory(httpx.MockTransport(handler))
    )

    result = await OrderGateway().place_order(_req())
    assert result.status == "SUBMITTED"
    assert result.order_id == "ORD123"
    assert result.is_real_submission is True


@pytest.mark.asyncio
async def test_sandbox_without_token_is_rejected_before_network(monkeypatch):
    monkeypatch.setenv("UPSTOX_EXECUTION_MODE", "SANDBOX")
    monkeypatch.delenv("UPSTOX_SANDBOX_ACCESS_TOKEN", raising=False)

    def explode(*a, **kw):
        raise AssertionError("must not call the network without a token")

    monkeypatch.setattr(gw_module.httpx, "AsyncClient", explode)

    result = await OrderGateway().place_order(_req())
    assert result.status == "REJECTED"
    assert result.is_real_submission is False


@pytest.mark.asyncio
async def test_live_mode_targets_the_hft_host(monkeypatch):
    monkeypatch.setenv("UPSTOX_EXECUTION_MODE", "LIVE")
    monkeypatch.setenv("UPSTOX_LIVE_TRADING_CONFIRMED", "YES")
    monkeypatch.setattr(gw_module.upstox_auth, "load_token", lambda: "live-token")

    def handler(request):
        assert "api-hft.upstox.com" in str(request.url)
        return httpx.Response(200, json={"status": "success", "data": {"order_id": "LIVE1"}})

    monkeypatch.setattr(
        gw_module.httpx, "AsyncClient", _mock_client_factory(httpx.MockTransport(handler))
    )

    result = await OrderGateway().place_order(_req())
    assert result.mode is ExecutionMode.LIVE
    assert result.order_id == "LIVE1"


# --------------------------- failure honesty ---------------------------

@pytest.mark.asyncio
async def test_broker_rejection_is_not_reported_as_submitted(monkeypatch):
    monkeypatch.setenv("UPSTOX_EXECUTION_MODE", "SANDBOX")
    monkeypatch.setenv("UPSTOX_SANDBOX_ACCESS_TOKEN", "sbx")

    def handler(request):
        return httpx.Response(400, json={"status": "error", "errors": [{"message": "bad qty"}]})

    monkeypatch.setattr(
        gw_module.httpx, "AsyncClient", _mock_client_factory(httpx.MockTransport(handler))
    )

    result = await OrderGateway().place_order(_req())
    assert result.status == "REJECTED"
    assert result.is_real_submission is False
    assert "bad qty" in result.detail


@pytest.mark.asyncio
async def test_transport_failure_reports_unknown_not_submitted(monkeypatch):
    """A network failure means we genuinely don't know if the broker got
    the order. It must never be reported as submitted."""
    monkeypatch.setenv("UPSTOX_EXECUTION_MODE", "SANDBOX")
    monkeypatch.setenv("UPSTOX_SANDBOX_ACCESS_TOKEN", "sbx")

    def handler(request):
        raise httpx.ConnectError("connection reset")

    monkeypatch.setattr(
        gw_module.httpx, "AsyncClient", _mock_client_factory(httpx.MockTransport(handler))
    )

    result = await OrderGateway().place_order(_req())
    assert result.status == "ERROR"
    assert result.is_real_submission is False
    assert "UNKNOWN" in result.detail


@pytest.mark.asyncio
async def test_200_without_order_id_is_not_submitted(monkeypatch):
    monkeypatch.setenv("UPSTOX_EXECUTION_MODE", "SANDBOX")
    monkeypatch.setenv("UPSTOX_SANDBOX_ACCESS_TOKEN", "sbx")

    def handler(request):
        return httpx.Response(200, json={"status": "success", "data": {}})

    monkeypatch.setattr(
        gw_module.httpx, "AsyncClient", _mock_client_factory(httpx.MockTransport(handler))
    )

    result = await OrderGateway().place_order(_req())
    assert result.status == "ERROR"
    assert result.is_real_submission is False
