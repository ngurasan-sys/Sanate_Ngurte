import httpx
import pytest

from backend.app.market_data import futures_instrument as futures_instrument_module
from backend.app.market_data.futures_instrument import (
    FuturesInstrumentCache,
    FuturesInstrumentLookupError,
    fetch_current_month_future_key,
)

_RealAsyncClient = httpx.AsyncClient


def _mock_client_factory(transport):
    return lambda *a, **kw: _RealAsyncClient(transport=transport)


SAMPLE_RESPONSE = {
    "status": "success",
    "data": [{
        "instrument_key": "NSE_FO|26000",
        "trading_symbol": "NIFTY26AUGFUT",
        "instrument_type": "FUT",
        "expiry": "2026-08-25",
    }],
}


@pytest.mark.asyncio
async def test_fetch_current_month_future_key_success(monkeypatch):
    def handler(request):
        assert request.url.path == "/v2/instruments/search"
        assert request.url.params["query"] == "NIFTY"
        assert request.url.params["instrument_types"] == "FUT"
        assert request.url.params["expiry"] == "current_month"
        return httpx.Response(200, json=SAMPLE_RESPONSE)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(futures_instrument_module.httpx, "AsyncClient", _mock_client_factory(transport))

    key = await fetch_current_month_future_key("NIFTY", "fake-token")
    assert key == "NSE_FO|26000"


@pytest.mark.asyncio
async def test_fetch_current_month_future_key_empty_raises(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"status": "success", "data": []})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(futures_instrument_module.httpx, "AsyncClient", _mock_client_factory(transport))

    with pytest.raises(FuturesInstrumentLookupError):
        await fetch_current_month_future_key("NIFTY", "fake-token")


@pytest.mark.asyncio
async def test_fetch_current_month_future_key_http_error_raises(monkeypatch):
    def handler(request):
        return httpx.Response(500, json={"status": "error"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(futures_instrument_module.httpx, "AsyncClient", _mock_client_factory(transport))

    with pytest.raises(FuturesInstrumentLookupError):
        await fetch_current_month_future_key("NIFTY", "fake-token")


@pytest.mark.asyncio
async def test_cache_reuses_same_day_result(monkeypatch):
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=SAMPLE_RESPONSE)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(futures_instrument_module.httpx, "AsyncClient", _mock_client_factory(transport))

    cache = FuturesInstrumentCache()
    key1 = await cache.get("NIFTY", "fake-token")
    key2 = await cache.get("NIFTY", "fake-token")

    assert key1 == key2 == "NSE_FO|26000"
    assert call_count == 1  # second call served from cache


@pytest.mark.asyncio
async def test_cache_tracks_underlyings_independently(monkeypatch):
    def handler(request):
        query = request.url.params["query"]
        key = "NSE_FO|26000" if query == "NIFTY" else "NSE_FO|26500"
        return httpx.Response(200, json={
            "status": "success",
            "data": [{"instrument_key": key, "trading_symbol": f"{query}FUT", "instrument_type": "FUT", "expiry": "2026-08-25"}],
        })

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(futures_instrument_module.httpx, "AsyncClient", _mock_client_factory(transport))

    cache = FuturesInstrumentCache()
    nifty_key = await cache.get("NIFTY", "fake-token")
    banknifty_key = await cache.get("BANKNIFTY", "fake-token")

    assert nifty_key == "NSE_FO|26000"
    assert banknifty_key == "NSE_FO|26500"
