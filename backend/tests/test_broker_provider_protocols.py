from backend.app.execution.broker_adapter import BrokerExecutionAdapter
from backend.app.market_data.provider import MarketDataProvider


class _FakeProvider:
    def instrument_key_for_index(self, underlying):
        return f"FAKE|{underlying}"

    async def connect_feed(self):
        pass

    async def disconnect_feed(self):
        pass

    async def fetch_option_chain(self, index_key, access_token, expiry_date="current_week"):
        return []

    async def fetch_quote(self, instrument_key, access_token):
        return None

    async def fetch_historical_candles(self, instrument_key, access_token, to_date, from_date, interval="day"):
        return []


class _IncompleteProvider:
    def instrument_key_for_index(self, underlying):
        return underlying


class _FakeAdapter:
    async def place_order(self, request, mode):
        return None


class _IncompleteAdapter:
    pass


def test_fake_provider_satisfies_protocol():
    assert isinstance(_FakeProvider(), MarketDataProvider)


def test_incomplete_provider_does_not_satisfy_protocol():
    assert not isinstance(_IncompleteProvider(), MarketDataProvider)


def test_fake_adapter_satisfies_protocol():
    assert isinstance(_FakeAdapter(), BrokerExecutionAdapter)


def test_incomplete_adapter_does_not_satisfy_protocol():
    assert not isinstance(_IncompleteAdapter(), BrokerExecutionAdapter)
