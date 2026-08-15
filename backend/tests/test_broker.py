from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.endpoints.broker import router as broker_router

app = FastAPI()
app.include_router(broker_router)
client = TestClient(app)


def test_login_redirects_to_real_upstox_url(monkeypatch):
    monkeypatch.setenv("UPSTOX_API_KEY", "my-client-id")
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/api/v1/broker/upstox/callback")

    response = client.get("/api/v1/broker/upstox/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    location = response.headers["location"]
    assert location.startswith("https://api.upstox.com/v2/login/authorization/dialog?")
    assert "client_id=my-client-id" in location


def test_callback_success_saves_token_and_configures_client():
    with patch(
        "backend.app.api.endpoints.broker.upstox_auth.exchange_code_for_token",
        new=AsyncMock(return_value="live-token-xyz"),
    ) as mock_exchange, patch(
        "backend.app.api.endpoints.broker.upstox_auth.save_token"
    ) as mock_save, patch(
        "backend.app.api.endpoints.broker.upstox_client"
    ) as mock_client:
        mock_client.connect = AsyncMock()

        response = client.get(
            "/api/v1/broker/upstox/callback?code=auth-code-123&state=xyz"
        )

        assert response.status_code == 200
        assert "Upstox Connected" in response.text
        mock_exchange.assert_awaited_once_with("auth-code-123")
        mock_save.assert_called_once_with("live-token-xyz")
        mock_client.configure.assert_called_once_with("live-token-xyz")
        mock_client.connect.assert_awaited_once()


def test_callback_failure_renders_error_page():
    from backend.app.core.upstox_auth import UpstoxAuthError

    with patch(
        "backend.app.api.endpoints.broker.upstox_auth.exchange_code_for_token",
        new=AsyncMock(side_effect=UpstoxAuthError("invalid_grant")),
    ):
        response = client.get(
            "/api/v1/broker/upstox/callback?code=bad-code&state=xyz"
        )

        assert response.status_code == 502
        assert "Upstox Connection Failed" in response.text
