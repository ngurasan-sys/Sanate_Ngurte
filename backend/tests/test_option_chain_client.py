import httpx
import pytest

from backend.app.market_data import option_chain_client as option_chain_client_module
from backend.app.market_data.option_chain_client import (
    OptionChainLookupError,
    fetch_option_chain,
)

_RealAsyncClient = httpx.AsyncClient


def _mock_client_factory(transport):
    return lambda *a, **kw: _RealAsyncClient(transport=transport)


SAMPLE_ROW = {
    "expiry": "2026-08-21",
    "pcr": 1.1,
    "strike_price": 24500,
    "underlying_key": "NSE_INDEX|Nifty 50",
    "underlying_spot_price": 24510.5,
    "call_options": {
        "market_data": {
            "ltp": 120.5, "close_price": 100.0, "volume": 5000,
            "oi": 800000, "prev_oi": 700000,
            "instrument_key": "NSE_FO|CE1",
        },
        "option_greeks": {"delta": 0.5, "gamma": 0.001, "vega": 10.0, "theta": -5.0, "iv": 14.0},
    },
    "put_options": {
        "market_data": {
            "ltp": 90.0, "close_price": 100.0, "volume": 4000,
            "oi": 600000, "prev_oi": 750000,
            "instrument_key": "NSE_FO|PE1",
        },
        "option_greeks": {"delta": -0.5, "gamma": 0.001, "vega": 10.0, "theta": -5.0, "iv": 13.0},
    },
}


@pytest.mark.asyncio
async def test_fetch_option_chain_success(monkeypatch):
    def handler(request):
        assert request.url.path == "/v2/option/chain"
        assert request.url.params["instrument_key"] == "NSE_INDEX|Nifty 50"
        assert request.url.params["expiry_date"] == "current_week"
        return httpx.Response(200, json={"status": "success", "data": [SAMPLE_ROW]})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        option_chain_client_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    chain = await fetch_option_chain("NSE_INDEX|Nifty 50", "fake-token")
    assert len(chain) == 1
    assert chain[0]["strike_price"] == 24500
    assert chain[0]["underlying_spot_price"] == 24510.5
    assert chain[0]["call_options"]["market_data"]["oi"] == 800000


@pytest.mark.asyncio
async def test_fetch_option_chain_empty_raises(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"status": "success", "data": []})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        option_chain_client_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    with pytest.raises(OptionChainLookupError):
        await fetch_option_chain("NSE_INDEX|Nifty 50", "fake-token")


@pytest.mark.asyncio
async def test_fetch_option_chain_http_error_raises(monkeypatch):
    def handler(request):
        return httpx.Response(401, json={"status": "error"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        option_chain_client_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    with pytest.raises(OptionChainLookupError):
        await fetch_option_chain("NSE_INDEX|Nifty 50", "fake-token")


@pytest.mark.asyncio
async def test_fetch_option_chain_transport_error_raises(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        option_chain_client_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    with pytest.raises(OptionChainLookupError):
        await fetch_option_chain("NSE_INDEX|Nifty 50", "fake-token")
