import httpx
import pytest

from backend.app.execution import dhan_adapter as da_module
from backend.app.execution.dhan_adapter import DhanExecutionAdapter
from backend.app.execution.order_gateway import ExecutionMode, OrderRequest

_RealAsyncClient = httpx.AsyncClient


def _req(**kw):
    defaults = dict(instrument_token="1001", transaction_type="BUY", quantity=75, product="I", order_type="MARKET")
    defaults.update(kw)
    return OrderRequest(**defaults)


@pytest.mark.asyncio
async def test_sandbox_mode_is_rejected_with_no_sandbox_reason(monkeypatch):
    def explode(*a, **kw):
        raise AssertionError("must not call the network for SANDBOX")
    monkeypatch.setattr(da_module.httpx, "AsyncClient", explode)

    result = await DhanExecutionAdapter().place_order(_req(), ExecutionMode.SANDBOX)

    assert result.status == "REJECTED"
    assert "sandbox" in result.detail.lower()


@pytest.mark.asyncio
async def test_live_submission_maps_fields_and_returns_order_id(monkeypatch):
    monkeypatch.setattr(da_module.dhan_auth, "load_token", lambda: "live-token")
    monkeypatch.setattr(da_module.dhan_auth, "load_client_id", lambda: "CLIENT123")

    captured = {}

    def handler(request):
        import json
        body = json.loads(request.content)
        captured.update(body)
        assert request.headers["access-token"] == "live-token"
        return httpx.Response(200, json={"orderId": "DHAN789", "orderStatus": "PENDING"})

    monkeypatch.setattr(da_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))

    result = await DhanExecutionAdapter().place_order(
        _req(product="D", order_type="SL", price=101.5, trigger_price=100.0), ExecutionMode.LIVE,
    )

    assert result.status == "SUBMITTED"
    assert result.order_id == "DHAN789"
    assert captured["dhanClientId"] == "CLIENT123"
    assert captured["transactionType"] == "BUY"
    assert captured["productType"] == "CNC"
    assert captured["orderType"] == "STOP_LOSS"
    assert captured["securityId"] == "1001"
    assert captured["quantity"] == 75


@pytest.mark.asyncio
async def test_no_order_id_in_response_is_not_submitted(monkeypatch):
    monkeypatch.setattr(da_module.dhan_auth, "load_token", lambda: "live-token")
    monkeypatch.setattr(da_module.dhan_auth, "load_client_id", lambda: "CLIENT123")

    def handler(request):
        return httpx.Response(200, json={"orderStatus": "REJECTED"})
    monkeypatch.setattr(da_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))

    result = await DhanExecutionAdapter().place_order(_req(), ExecutionMode.LIVE)

    assert result.status == "ERROR"
    assert result.is_real_submission is False


@pytest.mark.asyncio
async def test_missing_token_rejected_before_network(monkeypatch):
    monkeypatch.setattr(da_module.dhan_auth, "load_token", lambda: None)
    def explode(*a, **kw):
        raise AssertionError("must not call the network without a token")
    monkeypatch.setattr(da_module.httpx, "AsyncClient", explode)

    result = await DhanExecutionAdapter().place_order(_req(), ExecutionMode.LIVE)

    assert result.status == "REJECTED"


@pytest.mark.asyncio
async def test_order_id_with_rejected_status_is_not_submitted(monkeypatch):
    """Dhan can mint an orderId while still rejecting the order at the
    exchange leg — orderStatus must be checked, not just orderId presence."""
    monkeypatch.setattr(da_module.dhan_auth, "load_token", lambda: "live-token")
    monkeypatch.setattr(da_module.dhan_auth, "load_client_id", lambda: "CLIENT123")

    def handler(request):
        return httpx.Response(200, json={"orderId": "DHAN789", "orderStatus": "REJECTED"})
    monkeypatch.setattr(da_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))

    result = await DhanExecutionAdapter().place_order(_req(), ExecutionMode.LIVE)

    assert result.status == "REJECTED"
    assert result.is_real_submission is False


@pytest.mark.asyncio
async def test_malformed_json_body_is_error_not_exception(monkeypatch):
    monkeypatch.setattr(da_module.dhan_auth, "load_token", lambda: "live-token")
    monkeypatch.setattr(da_module.dhan_auth, "load_client_id", lambda: "CLIENT123")

    def handler(request):
        return httpx.Response(200, content=b"<html>not json</html>", headers={"content-type": "text/html"})
    monkeypatch.setattr(da_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))

    result = await DhanExecutionAdapter().place_order(_req(), ExecutionMode.LIVE)

    assert result.status == "ERROR"
    assert result.is_real_submission is False
    assert "UNKNOWN" in result.detail


@pytest.mark.asyncio
async def test_server_error_status_is_error_not_rejected(monkeypatch):
    """A 5xx could mean the order was actually accepted upstream and only
    the response got lost — it must not be reported as a clean rejection."""
    monkeypatch.setattr(da_module.dhan_auth, "load_token", lambda: "live-token")
    monkeypatch.setattr(da_module.dhan_auth, "load_client_id", lambda: "CLIENT123")

    def handler(request):
        return httpx.Response(503, text="Service Unavailable")
    monkeypatch.setattr(da_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))

    result = await DhanExecutionAdapter().place_order(_req(), ExecutionMode.LIVE)

    assert result.status == "ERROR"
    assert result.is_real_submission is False


@pytest.mark.asyncio
async def test_client_error_status_is_still_rejected(monkeypatch):
    """4xx (bad request / invalid params / insufficient funds) is a genuine
    client-side rejection, unlike a 5xx — must remain REJECTED."""
    monkeypatch.setattr(da_module.dhan_auth, "load_token", lambda: "live-token")
    monkeypatch.setattr(da_module.dhan_auth, "load_client_id", lambda: "CLIENT123")

    def handler(request):
        return httpx.Response(400, text="Bad Request")
    monkeypatch.setattr(da_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))

    result = await DhanExecutionAdapter().place_order(_req(), ExecutionMode.LIVE)

    assert result.status == "REJECTED"


# ---------------------- exchange segment is resolved, not hardcoded NSE ----------------------


async def _place_and_capture_segment(monkeypatch, instrument_token):
    monkeypatch.setattr(da_module.dhan_auth, "load_token", lambda: "live-token")
    monkeypatch.setattr(da_module.dhan_auth, "load_client_id", lambda: "CLIENT123")
    captured = {}

    def handler(request):
        import json
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"orderId": "DHAN789", "orderStatus": "PENDING"})

    monkeypatch.setattr(da_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))
    await DhanExecutionAdapter().place_order(_req(instrument_token=instrument_token), ExecutionMode.LIVE)
    return captured


@pytest.mark.asyncio
async def test_exchange_segment_is_resolved_from_the_instrument_master(monkeypatch):
    """SENSEX options live in BSE_FNO — hardcoding NSE_FNO would have Dhan
    reject (or worse, misroute) every SENSEX leg."""
    from unittest.mock import AsyncMock

    from backend.app.core.dhan_instrument_master import DhanInstrumentMaster

    csv_text = (
        "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_TRADING_SYMBOL,"
        "SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_INSTRUMENT_NAME\n"
        "NSE,D,1001,NIFTY-Oct2026-25000-CE,NIFTY 25000 CE,2026-10-30,25000,CE,OPTIDX\n"
        "BSE,D,7001,SENSEX-Oct2026-82000-CE,SENSEX 82000 CE,2026-10-30,82000,CE,OPTIDX\n"
    )
    master = DhanInstrumentMaster()
    monkeypatch.setattr(master, "_fetch_csv_text", AsyncMock(return_value=csv_text))
    await master.ensure_loaded()
    monkeypatch.setattr(da_module, "dhan_instrument_master", master)

    assert (await _place_and_capture_segment(monkeypatch, "1001"))["exchangeSegment"] == "NSE_FNO"
    assert (await _place_and_capture_segment(monkeypatch, "7001"))["exchangeSegment"] == "BSE_FNO"


@pytest.mark.asyncio
async def test_exchange_segment_falls_back_to_nse_when_master_is_unloaded(monkeypatch):
    from backend.app.core.dhan_instrument_master import DhanInstrumentMaster

    monkeypatch.setattr(da_module, "dhan_instrument_master", DhanInstrumentMaster())

    assert (await _place_and_capture_segment(monkeypatch, "1001"))["exchangeSegment"] == "NSE_FNO"
