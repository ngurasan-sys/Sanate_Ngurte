from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def test_startup_configures_client_when_token_exists():
    with patch(
        "backend.app.main.upstox_auth.load_token", return_value="saved-token-abc"
    ), patch("backend.app.main.upstox_client") as mock_client:
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()

        from backend.app.main import app

        with TestClient(app):
            pass

        mock_client.configure.assert_called_once_with("saved-token-abc")


def test_startup_skips_configure_when_no_token():
    with patch(
        "backend.app.main.upstox_auth.load_token", return_value=None
    ), patch("backend.app.main.upstox_client") as mock_client:
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()

        from backend.app.main import app

        with TestClient(app):
            pass

        mock_client.configure.assert_not_called()
