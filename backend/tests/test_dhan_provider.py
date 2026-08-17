# backend/tests/test_dhan_provider.py
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from backend.app.market_data import dhan_provider as dp_module
from backend.app.market_data.dhan_provider import DhanProvider, DhanProviderError
from backend.app.market_data.provider import MarketDataProvider

# dhan_instrument_master.security_id_for_index/security_id_for_option are
# synchronous (see backend/app/core/dhan_instrument_master.py) and are never
# awaited by DhanProvider, so the mock must be MagicMock, not AsyncMock.
_RealAsyncClient = httpx.AsyncClient


@pytest.fixture
def provider(monkeypatch):
    p = DhanProvider()
    master = MagicMock()
    # ensure_loaded() is awaited by fetch_option_chain()/connect_feed() now.
    master.ensure_loaded = AsyncMock()
    master.underlying_for_security_id.side_effect = lambda sid: {"13": "NIFTY"}.get(str(sid))
    master.is_index_security_id.side_effect = lambda sid: str(sid) == "13"
    master.exchange_for_security_id.side_effect = lambda sid: {"13": "NSE", "1001": "NSE"}.get(str(sid))
    master.security_id_for_index.return_value = "13"
    master.security_id_for_option.side_effect = lambda underlying, expiry, strike, opt_type: {
        ("NIFTY", "2026-10-30", 25000.0, "CE"): "1001",
        ("NIFTY", "2026-10-30", 25000.0, "PE"): "1002",
    }[(underlying, expiry, strike, opt_type)]
    monkeypatch.setattr(dp_module, "dhan_instrument_master", master)
    return p


def test_dhan_provider_satisfies_protocol():
    assert isinstance(DhanProvider(), MarketDataProvider)


def test_instrument_key_for_index_delegates_to_instrument_master(provider):
    assert provider.instrument_key_for_index("NIFTY") == "13"


@pytest.mark.asyncio
async def test_fetch_option_chain_translates_to_canonical_shape(provider, monkeypatch):
    def handler(request):
        assert request.url.path == "/v2/optionchain"
        return httpx.Response(200, json={
            "data": {"last_price": 25010.5, "oc": {"25000.000000": {
                "ce": {"last_price": 120.5, "oi": 500000, "volume": 12000,
                       "top_bid_price": 119.0, "top_ask_price": 121.0, "implied_volatility": 15.2,
                       "greeks": {"delta": 0.5, "gamma": 0.001, "theta": -5.0, "vega": 10.0}},
                "pe": {"last_price": 80.0, "oi": 300000, "volume": 8000,
                       "top_bid_price": 79.0, "top_ask_price": 81.0, "implied_volatility": 14.8,
                       "greeks": {"delta": -0.5, "gamma": 0.001, "theta": -4.5, "vega": 9.5}},
            }}},
        })
    monkeypatch.setattr(dp_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))

    chain = await provider.fetch_option_chain("13", "tok", "2026-10-30")

    assert len(chain) == 1
    row = chain[0]
    assert row["strike_price"] == 25000.0
    assert row["expiry"] == "2026-10-30"
    assert row["underlying_spot_price"] == 25010.5
    assert row["call_options"]["instrument_key"] == "1001"
    assert row["call_options"]["market_data"]["bid_price"] == 119.0
    assert row["call_options"]["market_data"]["ask_price"] == 121.0
    assert row["call_options"]["market_data"]["ltp"] == 120.5
    assert row["call_options"]["market_data"]["oi"] == 500000
    assert row["call_options"]["option_greeks"]["iv"] == 15.2
    assert row["call_options"]["option_greeks"]["delta"] == 0.5
    assert row["put_options"]["instrument_key"] == "1002"
    assert row["put_options"]["market_data"]["ltp"] == 80.0


@pytest.mark.asyncio
async def test_fetch_option_chain_logs_warning_on_security_id_resolution_failure(provider, monkeypatch, caplog):
    def handler(request):
        return httpx.Response(200, json={
            "data": {"last_price": 25010.5, "oc": {"25000.000000": {
                "ce": {"last_price": 120.5, "oi": 500000, "volume": 12000,
                       "top_bid_price": 119.0, "top_ask_price": 121.0, "implied_volatility": 15.2,
                       "greeks": {"delta": 0.5, "gamma": 0.001, "theta": -5.0, "vega": 10.0}},
            }}},
        })
    monkeypatch.setattr(dp_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))
    dp_module.dhan_instrument_master.security_id_for_option.side_effect = KeyError("not found")

    with caplog.at_level("WARNING"):
        chain = await provider.fetch_option_chain("13", "tok", "2026-10-30")

    assert chain[0]["call_options"]["instrument_key"] is None
    assert any("security_id resolution failed" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_fetch_quote_translates_to_canonical_quote(provider, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={
            "data": {"NSE": {"13": {"last_price": 25010.5, "volume": 999,
                                     "depth": {"buy": [{"price": 25009.0}], "sell": [{"price": 25011.0}]}}}}
        })
    monkeypatch.setattr(dp_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))

    quote = await provider.fetch_quote("13", "tok")

    assert quote.last_price == 25010.5
    assert quote.bid == 25009.0
    assert quote.ask == 25011.0
    assert quote.volume == 999


@pytest.mark.asyncio
async def test_fetch_quote_raises_on_empty_data(provider, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"data": {}})
    monkeypatch.setattr(dp_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))

    with pytest.raises(DhanProviderError):
        await provider.fetch_quote("13", "tok")


@pytest.mark.asyncio
async def test_fetch_historical_candles_translates_to_canonical_rows(provider, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={
            "open": [100.0, 105.0], "high": [110.0, 108.0], "low": [95.0, 102.0],
            "close": [105.0, 107.0], "volume": [1000, 1200],
            "timestamp": [1735689000, 1735775400],
        })
    monkeypatch.setattr(dp_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))

    rows = await provider.fetch_historical_candles("13", "tok", date(2025, 1, 2), date(2025, 1, 1), "day")

    assert len(rows) == 2
    assert rows[0]["close"] == 105.0
    assert rows[0]["volume"] == 1000
    assert "timestamp" in rows[0]


# ---------------------- expiry resolution (Upstox vocabulary -> real Dhan date) ----------------------


def _expiry_and_chain_handler(recorded, expiries=("2026-10-30", "2026-11-06")):
    def handler(request):
        import json as _json
        body = _json.loads(request.content.decode())
        recorded.append((request.url.path, body))
        if request.url.path.endswith("/optionchain/expirylist"):
            return httpx.Response(200, json={"status": "success", "data": list(expiries)})
        return httpx.Response(200, json={
            "data": {"last_price": 25010.5, "oc": {"25000.000000": {
                "ce": {"last_price": 120.5, "oi": 5, "volume": 1, "top_bid_price": 119.0,
                       "top_ask_price": 121.0, "implied_volatility": 15.2, "greeks": {}},
            }}},
        })
    return handler


@pytest.mark.asyncio
async def test_current_week_resolves_to_first_dhan_expiry(provider, monkeypatch):
    recorded = []
    monkeypatch.setattr(dp_module.httpx, "AsyncClient",
                        lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(_expiry_and_chain_handler(recorded))))

    chain = await provider.fetch_option_chain("13", "tok", "current_week")

    paths = [p for p, _ in recorded]
    assert paths == ["/v2/optionchain/expirylist", "/v2/optionchain"]
    # The expiry-list request identifies the underlying correctly...
    assert recorded[0][1] == {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}
    # ...and the resolved real date (not "current_week") is what Dhan is asked for.
    assert recorded[1][1]["Expiry"] == "2026-10-30"
    assert chain[0]["expiry"] == "2026-10-30"
    # ...and the same real date is what the security_id lookup used.
    dp_module.dhan_instrument_master.security_id_for_option.assert_called_with(
        "NIFTY", "2026-10-30", 25000.0, "CE",
    )
    assert chain[0]["call_options"]["instrument_key"] == "1001"


@pytest.mark.asyncio
async def test_next_week_resolves_to_second_dhan_expiry(provider, monkeypatch):
    recorded = []
    monkeypatch.setattr(dp_module.httpx, "AsyncClient",
                        lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(_expiry_and_chain_handler(recorded))))

    resolved = await provider._resolve_expiry_date("13", "tok", "next_week")

    assert resolved == "2026-11-06"


@pytest.mark.asyncio
async def test_iso_expiry_is_passed_through_without_an_expirylist_call(provider, monkeypatch):
    recorded = []
    monkeypatch.setattr(dp_module.httpx, "AsyncClient",
                        lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(_expiry_and_chain_handler(recorded))))

    await provider.fetch_option_chain("13", "tok", "2026-10-30")

    assert [p for p, _ in recorded] == ["/v2/optionchain"]


@pytest.mark.asyncio
async def test_next_week_with_only_one_expiry_raises(provider, monkeypatch):
    recorded = []
    monkeypatch.setattr(dp_module.httpx, "AsyncClient",
                        lambda *a, **kw: _RealAsyncClient(
                            transport=httpx.MockTransport(_expiry_and_chain_handler(recorded, expiries=("2026-10-30",)))))

    with pytest.raises(DhanProviderError):
        await provider._resolve_expiry_date("13", "tok", "next_week")


# ---------------------- empty chain raises (fallback compatibility) ----------------------


@pytest.mark.asyncio
async def test_empty_option_chain_raises_instead_of_returning_empty_list(provider, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"data": {"last_price": 25010.5, "oc": {}}})
    monkeypatch.setattr(dp_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))

    with pytest.raises(DhanProviderError):
        await provider.fetch_option_chain("13", "tok", "2026-10-30")


# ---------------------- exception compatibility with Upstox-shaped except-clauses ----------------------


def test_dhan_errors_are_catchable_by_existing_strategy_except_clauses():
    from backend.app.core.dhan_instrument_master import DhanInstrumentLookupError
    from backend.app.market_data.market_quote import MarketQuoteLookupError
    from backend.app.market_data.option_chain_client import OptionChainLookupError

    assert issubclass(DhanProviderError, OptionChainLookupError)
    assert issubclass(DhanProviderError, MarketQuoteLookupError)
    assert issubclass(DhanInstrumentLookupError, KeyError)
    assert issubclass(DhanInstrumentLookupError, OptionChainLookupError)


def test_dhan_instrument_lookup_error_message_is_not_repr_quoted():
    from backend.app.core.dhan_instrument_master import DhanInstrumentLookupError
    assert str(DhanInstrumentLookupError("no security_id for NIFTY")) == "no security_id for NIFTY"


# ---------------------- exchange segments (SENSEX is BSE) ----------------------


@pytest.mark.asyncio
async def test_fetch_quote_uses_bse_segment_for_a_bse_instrument(provider, monkeypatch):
    recorded = {}

    def handler(request):
        import json as _json
        recorded.update(_json.loads(request.content.decode()))
        return httpx.Response(200, json={"data": {"BSE_FNO": {"7001": {"last_price": 10.0, "volume": 1, "depth": {}}}}})

    monkeypatch.setattr(dp_module.httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)))
    dp_module.dhan_instrument_master.is_index_security_id.side_effect = lambda sid: False
    dp_module.dhan_instrument_master.exchange_for_security_id.side_effect = lambda sid: "BSE"

    quote = await provider.fetch_quote("7001", "tok")

    assert list(recorded.keys()) == ["BSE_FNO"]
    assert quote.last_price == 10.0
