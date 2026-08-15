import httpx
import pytest

from backend.app.market_data import market_quote as market_quote_module
from backend.app.market_data.market_quote import MarketQuoteLookupError, fetch_quote

_RealAsyncClient = httpx.AsyncClient


def _mock_client_factory(transport):
    return lambda *a, **kw: _RealAsyncClient(transport=transport)


SAMPLE_RESPONSE = {
    "status": "success",
    "data": {
        "NSE_FO:26009": {
            "last_price": 24858.5,
            "volume": 123456,
            "depth": {
                "buy": [{"quantity": 50, "price": 24858.0, "orders": 3}],
                "sell": [{"quantity": 75, "price": 24859.0, "orders": 2}],
            },
        }
    },
}


@pytest.mark.asyncio
async def test_fetch_quote_success(monkeypatch):
    def handler(request):
        assert request.url.path == "/v2/market-quote/quotes"
        assert request.url.params["instrument_key"] == "NSE_FO|26009"
        return httpx.Response(200, json=SAMPLE_RESPONSE)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(market_quote_module.httpx, "AsyncClient", _mock_client_factory(transport))

    quote = await fetch_quote("NSE_FO|26009", "fake-token")
    assert quote.last_price == 24858.5
    assert quote.bid == 24858.0
    assert quote.ask == 24859.0
    assert quote.volume == 123456


@pytest.mark.asyncio
async def test_fetch_quote_missing_depth_returns_none_bid_ask(monkeypatch):
    response = {
        "status": "success",
        "data": {"NSE_FO:26009": {"last_price": 100.0, "volume": 10, "depth": {"buy": [], "sell": []}}},
    }

    def handler(request):
        return httpx.Response(200, json=response)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(market_quote_module.httpx, "AsyncClient", _mock_client_factory(transport))

    quote = await fetch_quote("NSE_FO|26009", "fake-token")
    assert quote.bid is None
    assert quote.ask is None


@pytest.mark.asyncio
async def test_fetch_quote_empty_data_raises(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"status": "success", "data": {}})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(market_quote_module.httpx, "AsyncClient", _mock_client_factory(transport))

    with pytest.raises(MarketQuoteLookupError):
        await fetch_quote("NSE_FO|26009", "fake-token")


@pytest.mark.asyncio
async def test_fetch_quote_http_error_raises(monkeypatch):
    def handler(request):
        return httpx.Response(401, json={"status": "error"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(market_quote_module.httpx, "AsyncClient", _mock_client_factory(transport))

    with pytest.raises(MarketQuoteLookupError):
        await fetch_quote("NSE_FO|26009", "fake-token")


@pytest.mark.asyncio
async def test_fetch_quote_transport_error_raises(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(market_quote_module.httpx, "AsyncClient", _mock_client_factory(transport))

    with pytest.raises(MarketQuoteLookupError):
        await fetch_quote("NSE_FO|26009", "fake-token")
