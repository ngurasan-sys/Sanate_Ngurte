import pytest

from backend.app.core import active_broker as ab_module


@pytest.mark.asyncio
async def test_upstox_registered_at_import_time():
    # main.py registers upstox with active_broker at import time (via
    # upstox_provider/upstox_adapter/upstox_auth) regardless of whether a
    # token is saved — readiness (is_broker_ready) is what gates activation.
    import backend.app.main  # noqa: F401 — import triggers registration
    assert "upstox" in ab_module.active_broker._registrations
    reg = ab_module.active_broker._registrations["upstox"]
    assert reg.provider is not None
    assert reg.execution_adapter is not None
    assert reg.auth_module is not None
