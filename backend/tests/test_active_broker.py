import pytest

from backend.app.core import active_broker as ab_module
from backend.app.core.active_broker import ActiveBrokerRegistry, BrokerSwitchError


class _FakeAuth:
    def __init__(self, token):
        self._token = token

    def load_token(self):
        return self._token


class _FakeProvider:
    def __init__(self):
        self.connected = False
        self.disconnected = False

    def instrument_key_for_index(self, underlying):
        return f"FAKE|{underlying}"

    async def connect_feed(self):
        self.connected = True

    async def disconnect_feed(self):
        self.disconnected = True

    async def fetch_option_chain(self, index_key, access_token, expiry_date="current_week"):
        return []

    async def fetch_quote(self, instrument_key, access_token):
        return None

    async def fetch_historical_candles(self, instrument_key, access_token, to_date, from_date, interval="day"):
        return []


class _FakeAdapter:
    async def place_order(self, request, mode):
        return None


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(ab_module, "STATE_PATH", tmp_path / "active_broker.json")
    monkeypatch.setattr(ab_module.event_bus, "publish", _noop_publish)
    return ActiveBrokerRegistry()


_published = []


async def _noop_publish(channel, payload):
    _published.append((channel, payload))


def test_no_active_broker_initially(registry):
    assert registry.get_active_broker_id() is None
    assert registry.get_active_provider() is None
    assert registry.get_active_execution_adapter() is None


def test_is_broker_ready_false_until_fully_registered_and_connected(registry):
    assert registry.is_broker_ready("upstox") is False
    registry.register_broker("upstox", provider=_FakeProvider())
    assert registry.is_broker_ready("upstox") is False  # no adapter/auth yet
    registry.register_broker("upstox", execution_adapter=_FakeAdapter(), auth_module=_FakeAuth(None))
    assert registry.is_broker_ready("upstox") is False  # auth has no token
    registry.register_broker("upstox", auth_module=_FakeAuth("tok"))
    assert registry.is_broker_ready("upstox") is True


@pytest.mark.asyncio
async def test_set_active_broker_rejects_unknown_broker(registry):
    with pytest.raises(BrokerSwitchError):
        await registry.set_active_broker("not_a_real_broker")


@pytest.mark.asyncio
async def test_set_active_broker_rejects_not_ready_broker(registry):
    with pytest.raises(BrokerSwitchError):
        await registry.set_active_broker("upstox")


@pytest.mark.asyncio
async def test_set_active_broker_succeeds_and_connects_feed(registry):
    provider = _FakeProvider()
    registry.register_broker("upstox", provider=provider, execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok"))
    await registry.set_active_broker("upstox")
    assert registry.get_active_broker_id() == "upstox"
    assert registry.get_active_provider() is provider
    assert provider.connected is True


@pytest.mark.asyncio
async def test_active_broker_persists_across_new_registry_instance(tmp_path, monkeypatch):
    state_path = tmp_path / "active_broker.json"
    monkeypatch.setattr(ab_module, "STATE_PATH", state_path)
    monkeypatch.setattr(ab_module.event_bus, "publish", _noop_publish)

    first = ActiveBrokerRegistry()
    first.register_broker("upstox", provider=_FakeProvider(), execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok"))
    await first.set_active_broker("upstox")

    second = ActiveBrokerRegistry()
    assert second.get_active_broker_id() == "upstox"


@pytest.mark.asyncio
async def test_switching_broker_disconnects_previous_provider(registry):
    upstox_provider = _FakeProvider()
    zerodha_provider = _FakeProvider()
    registry.register_broker("upstox", provider=upstox_provider, execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok"))
    registry.register_broker("zerodha", provider=zerodha_provider, execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok2"))

    await registry.set_active_broker("upstox")
    await registry.set_active_broker("zerodha")

    assert upstox_provider.disconnected is True
    assert zerodha_provider.connected is True
    assert registry.get_active_broker_id() == "zerodha"


@pytest.mark.asyncio
async def test_switch_blocked_by_open_position(registry):
    registry.register_broker("upstox", provider=_FakeProvider(), execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok"))
    registry.register_broker("zerodha", provider=_FakeProvider(), execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok2"))
    await registry.set_active_broker("upstox")

    registry.register_position_checker("CAS Dislocation", lambda: "1 open position (NIFTY 25000 CE)")

    with pytest.raises(BrokerSwitchError, match="CAS Dislocation"):
        await registry.set_active_broker("zerodha")
    assert registry.get_active_broker_id() == "upstox"  # unchanged


@pytest.mark.asyncio
async def test_switch_allowed_when_checker_reports_no_blocker(registry):
    registry.register_broker("upstox", provider=_FakeProvider(), execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok"))
    registry.register_broker("zerodha", provider=_FakeProvider(), execution_adapter=_FakeAdapter(), auth_module=_FakeAuth("tok2"))
    await registry.set_active_broker("upstox")

    registry.register_position_checker("CAS Dislocation", lambda: None)

    await registry.set_active_broker("zerodha")
    assert registry.get_active_broker_id() == "zerodha"
