from datetime import date, datetime

import httpx
import pytest

from backend.app.market_data import expiry_calendar as expiry_calendar_module
from backend.app.market_data.expiry_calendar import (
    ExpiryCalendar,
    ExpiryLookupError,
    IST,
    fetch_current_week_expiry,
)

# Capture the real httpx.AsyncClient BEFORE any test patches the name —
# the mocked factory below must construct real AsyncClient instances
# (bound to a MockTransport), not recurse into itself via the patched name.
_RealAsyncClient = httpx.AsyncClient


def _mock_client_factory(transport):
    return lambda *a, **kw: _RealAsyncClient(transport=transport)


@pytest.mark.asyncio
async def test_fetch_current_week_expiry_success(monkeypatch):
    def handler(request):
        assert request.url.path == "/v2/instruments/search"
        assert request.url.params["query"] == "NIFTY"
        assert request.url.params["expiry"] == "current_week"
        return httpx.Response(200, json={"status": "success", "data": [{"expiry": "2026-01-08"}]})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        expiry_calendar_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    expiry = await fetch_current_week_expiry("NIFTY", "fake-token")
    assert expiry == date(2026, 1, 8)


@pytest.mark.asyncio
async def test_fetch_current_week_expiry_empty_results_raises(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"status": "success", "data": []})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        expiry_calendar_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    with pytest.raises(ExpiryLookupError):
        await fetch_current_week_expiry("NIFTY", "fake-token")


@pytest.mark.asyncio
async def test_fetch_current_week_expiry_http_error_raises(monkeypatch):
    def handler(request):
        return httpx.Response(401, json={"status": "error", "errors": [{"message": "invalid token"}]})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        expiry_calendar_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    with pytest.raises(ExpiryLookupError):
        await fetch_current_week_expiry("NIFTY", "fake-token")


@pytest.mark.asyncio
async def test_fetch_current_week_expiry_transport_error_raises(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        expiry_calendar_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    with pytest.raises(ExpiryLookupError):
        await fetch_current_week_expiry("NIFTY", "fake-token")


@pytest.mark.asyncio
async def test_is_today_expiry_day_true(monkeypatch):
    today = datetime.now(IST).date()

    def handler(request):
        return httpx.Response(200, json={"status": "success", "data": [{"expiry": today.isoformat()}]})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        expiry_calendar_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    calendar = ExpiryCalendar()
    result = await calendar.is_today_expiry_day("NIFTY", "fake-token")
    assert result is True
    assert calendar.cached_expiry("NIFTY") == today


@pytest.mark.asyncio
async def test_is_today_expiry_day_false(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"status": "success", "data": [{"expiry": "2099-12-31"}]})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        expiry_calendar_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    calendar = ExpiryCalendar()
    result = await calendar.is_today_expiry_day("NIFTY", "fake-token")
    assert result is False


@pytest.mark.asyncio
async def test_is_today_expiry_day_uses_cache_without_second_request(monkeypatch):
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        return httpx.Response(200, json={"status": "success", "data": [{"expiry": "2099-12-31"}]})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        expiry_calendar_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    calendar = ExpiryCalendar()
    await calendar.is_today_expiry_day("NIFTY", "fake-token")
    await calendar.is_today_expiry_day("NIFTY", "fake-token")

    assert call_count["n"] == 1


def test_cached_expiry_returns_none_when_not_yet_resolved():
    calendar = ExpiryCalendar()
    assert calendar.cached_expiry("NIFTY") is None
