from datetime import date

import httpx
import pytest

from backend.app.market_data import historical_candles as historical_candles_module
from backend.app.market_data.historical_candles import (
    HistoricalCandleLookupError,
    closes_from_candles,
    fetch_historical_candles,
)

_RealAsyncClient = httpx.AsyncClient


def _mock_client_factory(transport):
    return lambda *a, **kw: _RealAsyncClient(transport=transport)


# Upstox returns newest-first; two days here, deliberately out of order.
SAMPLE_CANDLES = [
    ["2026-08-15T00:00:00+05:30", 24400.0, 24500.0, 24350.0, 24450.0, 1000, 0],
    ["2026-08-14T00:00:00+05:30", 24300.0, 24420.0, 24280.0, 24400.0, 900, 0],
]


@pytest.mark.asyncio
async def test_fetch_historical_candles_success_and_chronological_order(monkeypatch):
    def handler(request):
        assert request.url.path == "/v2/historical-candle/NSE_INDEX|Nifty 50/day/2026-08-15/2026-08-01"
        return httpx.Response(200, json={"status": "success", "data": {"candles": SAMPLE_CANDLES}})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        historical_candles_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    rows = await fetch_historical_candles(
        "NSE_INDEX|Nifty 50", "fake-token", date(2026, 8, 15), date(2026, 8, 1)
    )

    assert len(rows) == 2
    # Reversed to chronological order: 08-14 before 08-15.
    assert rows[0]["timestamp"] == "2026-08-14T00:00:00+05:30"
    assert rows[0]["close"] == 24400.0
    assert rows[1]["timestamp"] == "2026-08-15T00:00:00+05:30"
    assert rows[1]["close"] == 24450.0


@pytest.mark.asyncio
async def test_fetch_historical_candles_empty_raises(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"status": "success", "data": {"candles": []}})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        historical_candles_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    with pytest.raises(HistoricalCandleLookupError):
        await fetch_historical_candles(
            "NSE_INDEX|Nifty 50", "fake-token", date(2026, 8, 15), date(2026, 8, 1)
        )


@pytest.mark.asyncio
async def test_fetch_historical_candles_http_error_raises(monkeypatch):
    def handler(request):
        return httpx.Response(401, json={"status": "error"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        historical_candles_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    with pytest.raises(HistoricalCandleLookupError):
        await fetch_historical_candles(
            "NSE_INDEX|Nifty 50", "fake-token", date(2026, 8, 15), date(2026, 8, 1)
        )


@pytest.mark.asyncio
async def test_fetch_historical_candles_transport_error_raises(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        historical_candles_module.httpx, "AsyncClient", _mock_client_factory(transport)
    )

    with pytest.raises(HistoricalCandleLookupError):
        await fetch_historical_candles(
            "NSE_INDEX|Nifty 50", "fake-token", date(2026, 8, 15), date(2026, 8, 1)
        )


def test_closes_from_candles():
    rows = [{"close": 100.0}, {"close": 101.5}]
    assert closes_from_candles(rows) == [100.0, 101.5]
