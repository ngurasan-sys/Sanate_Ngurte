from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.core.active_broker import active_broker as real_active_broker
from backend.app.market_data import upstox_provider as upstox_provider_module


@pytest.fixture(autouse=True)
def _reset_active_broker_state():
    """The active_broker singleton is process-wide and persists activation
    to disk (STATE_PATH). Snapshot/restore both the in-memory id and the
    persisted file so these tests don't leak broker-active state into
    other tests in the same run."""
    original_id = real_active_broker._active_broker_id
    from backend.app.core.active_broker import STATE_PATH

    existed = STATE_PATH.exists()
    original_bytes = STATE_PATH.read_bytes() if existed else None

    real_active_broker._active_broker_id = None
    try:
        yield
    finally:
        real_active_broker._active_broker_id = original_id
        if existed:
            STATE_PATH.write_bytes(original_bytes)
        elif STATE_PATH.exists():
            STATE_PATH.unlink()


def test_startup_activates_upstox_when_token_exists():
    # Behavior preserved from the pre-multi-broker implementation: if a
    # saved Upstox token exists and no broker is already active, Upstox is
    # activated automatically on startup, and — critically — the real
    # feed is actually *configured* with that token (not just marked
    # "active" while silently running in mock mode). Exercises the real
    # active_broker singleton and the real UpstoxProvider.connect_feed(),
    # only mocking the network-touching upstox_client.configure/connect
    # calls underneath.
    with patch(
        "backend.app.main.upstox_auth.load_token", return_value="saved-token-abc"
    ), patch.object(
        upstox_provider_module.upstox_client, "configure"
    ) as mock_configure, patch.object(
        upstox_provider_module.upstox_client, "connect", new=AsyncMock()
    ) as mock_connect, patch.object(
        upstox_provider_module.upstox_client, "close", new=AsyncMock()
    ):
        from backend.app.main import app

        with TestClient(app):
            pass

        mock_configure.assert_called_once_with("saved-token-abc")
        mock_connect.assert_awaited()
        assert real_active_broker.get_active_broker_id() == "upstox"


def test_startup_skips_activation_when_no_token():
    with patch(
        "backend.app.main.upstox_auth.load_token", return_value=None
    ), patch.object(
        upstox_provider_module.upstox_client, "configure"
    ) as mock_configure, patch.object(
        upstox_provider_module.upstox_client, "connect", new=AsyncMock()
    ) as mock_connect, patch.object(
        upstox_provider_module.upstox_client, "close", new=AsyncMock()
    ):
        from backend.app.main import app

        with TestClient(app):
            pass

        mock_configure.assert_not_called()
        mock_connect.assert_not_called()
        assert real_active_broker.get_active_broker_id() is None
