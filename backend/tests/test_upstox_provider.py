from datetime import date
from unittest.mock import AsyncMock

import pytest

from backend.app.market_data import upstox_provider as up_module
from backend.app.market_data.provider import MarketDataProvider
from backend.app.market_data.upstox_provider import UpstoxProvider


def test_upstox_provider_satisfies_protocol():
    assert isinstance(UpstoxProvider(), MarketDataProvider)


def test_instrument_key_for_index_uses_symbols_mapping():
    provider = UpstoxProvider()
    assert provider.instrument_key_for_index("NIFTY") == "NSE_INDEX|Nifty 50"


@pytest.mark.asyncio
async def test_connect_feed_delegates_to_upstox_client(monkeypatch):
    provider = UpstoxProvider()
    mock_connect = AsyncMock()
    monkeypatch.setattr(up_module.upstox_client, "connect", mock_connect)
    await provider.connect_feed()
    mock_connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_feed_delegates_to_upstox_client_close(monkeypatch):
    provider = UpstoxProvider()
    mock_close = AsyncMock()
    monkeypatch.setattr(up_module.upstox_client, "close", mock_close)
    await provider.disconnect_feed()
    mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_option_chain_delegates_with_same_args(monkeypatch):
    provider = UpstoxProvider()
    mock_fetch = AsyncMock(return_value=[{"strike_price": 25000}])
    monkeypatch.setattr(up_module, "fetch_option_chain", mock_fetch)
    result = await provider.fetch_option_chain("NSE_INDEX|Nifty 50", "tok", "current_week")
    mock_fetch.assert_awaited_once_with("NSE_INDEX|Nifty 50", "tok", "current_week")
    assert result == [{"strike_price": 25000}]


@pytest.mark.asyncio
async def test_fetch_quote_delegates(monkeypatch):
    provider = UpstoxProvider()
    mock_fetch = AsyncMock(return_value="quote-object")
    monkeypatch.setattr(up_module, "fetch_quote", mock_fetch)
    result = await provider.fetch_quote("NSE_FO|123", "tok")
    mock_fetch.assert_awaited_once_with("NSE_FO|123", "tok")
    assert result == "quote-object"


@pytest.mark.asyncio
async def test_fetch_historical_candles_delegates(monkeypatch):
    provider = UpstoxProvider()
    mock_fetch = AsyncMock(return_value=[{"close": 100.0}])
    monkeypatch.setattr(up_module, "fetch_historical_candles", mock_fetch)
    to_date, from_date = date(2026, 1, 10), date(2026, 1, 1)
    result = await provider.fetch_historical_candles("NSE_INDEX|Nifty 50", "tok", to_date, from_date, "day")
    mock_fetch.assert_awaited_once_with("NSE_INDEX|Nifty 50", "tok", to_date, from_date, "day")
    assert result == [{"close": 100.0}]
