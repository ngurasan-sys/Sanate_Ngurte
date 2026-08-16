from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def test_startup_activates_upstox_when_token_exists():
    # Behavior preserved from the pre-multi-broker implementation: if a
    # saved Upstox token exists and no broker is already active, Upstox
    # is activated automatically on startup. Post-Task-7 this happens via
    # active_broker.set_active_broker("upstox") rather than a direct
    # upstox_client.configure()/connect() call.
    with patch(
        "backend.app.main.upstox_auth.load_token", return_value="saved-token-abc"
    ), patch("backend.app.main.active_broker") as mock_active_broker:
        mock_active_broker.get_active_broker_id.return_value = None
        mock_active_broker.is_broker_ready.return_value = True
        mock_active_broker.set_active_broker = AsyncMock()
        mock_active_broker.get_active_provider.return_value = None

        from backend.app.main import app

        with TestClient(app):
            pass

        mock_active_broker.set_active_broker.assert_called_once_with("upstox")


def test_startup_skips_activation_when_no_token():
    with patch(
        "backend.app.main.upstox_auth.load_token", return_value=None
    ), patch("backend.app.main.active_broker") as mock_active_broker:
        mock_active_broker.get_active_broker_id.return_value = None
        mock_active_broker.is_broker_ready.return_value = False
        mock_active_broker.set_active_broker = AsyncMock()
        mock_active_broker.get_active_provider.return_value = None

        from backend.app.main import app

        with TestClient(app):
            pass

        mock_active_broker.set_active_broker.assert_not_called()
