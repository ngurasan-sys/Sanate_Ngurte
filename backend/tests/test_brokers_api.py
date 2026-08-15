from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.endpoints.brokers import router as brokers_router
from backend.app.core import credential_store, upstox_auth

app = FastAPI()
app.include_router(brokers_router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setattr(credential_store, "STORE_PATH", tmp_path / ".broker_credentials.json")
    monkeypatch.setattr(credential_store, "KEY_PATH", tmp_path / ".credential_key")
    # A real backend/.token.json may exist on this machine from manual
    # Upstox OAuth testing — isolate it so "connected" reflects only what
    # this test itself set up, not leftover state from earlier sessions.
    monkeypatch.setattr(upstox_auth, "TOKEN_PATH", tmp_path / ".token.json")


def test_list_brokers_returns_all_three_disconnected_by_default():
    response = client.get("/api/v1/brokers")

    assert response.status_code == 200
    body = response.json()
    ids = {b["id"] for b in body}
    assert ids == {"upstox", "zerodha", "dhan"}
    assert all(b["connected"] is False for b in body)


def test_list_brokers_never_includes_secret_values():
    response = client.get("/api/v1/brokers")
    body_text = response.text
    for field_dict in [f for b in response.json() for f in b["fields"]]:
        assert "value" not in field_dict


def test_unknown_broker_status_returns_404():
    response = client.get("/api/v1/brokers/robinhood/status")
    assert response.status_code == 404


def test_save_credentials_for_upstox():
    response = client.post(
        "/api/v1/brokers/upstox/credentials",
        json={"fields": {"api_key": "k", "api_secret": "s", "redirect_uri": "http://x/callback"}},
    )

    assert response.status_code == 200
    assert credential_store.load_credentials("upstox") == {
        "api_key": "k", "api_secret": "s", "redirect_uri": "http://x/callback",
    }


def test_save_credentials_rejects_missing_fields():
    response = client.post(
        "/api/v1/brokers/upstox/credentials",
        json={"fields": {"api_key": "k"}},
    )
    assert response.status_code == 400


def test_save_credentials_rejects_unknown_fields():
    response = client.post(
        "/api/v1/brokers/upstox/credentials",
        json={"fields": {"api_key": "k", "api_secret": "s", "redirect_uri": "u", "pin": "1234"}},
    )
    assert response.status_code == 400


def test_save_credentials_rejects_dhan_which_uses_token_endpoint_instead():
    response = client.post(
        "/api/v1/brokers/dhan/credentials",
        json={"fields": {"client_id": "x", "access_token": "y"}},
    )
    assert response.status_code == 400


def test_delete_credentials_clears_stored_values():
    credential_store.save_credentials("upstox", {"api_key": "k"})

    response = client.delete("/api/v1/brokers/upstox/credentials")

    assert response.status_code == 200
    assert credential_store.load_credentials("upstox") is None


def test_login_without_saved_credentials_returns_400(monkeypatch):
    # backend/app/main.py's load_dotenv() call permanently sets these in
    # os.environ for the rest of the pytest process once anything imports
    # main — isolate them here so this test reflects "nothing saved",
    # not whatever backend/.env happens to contain on this machine.
    monkeypatch.delenv("UPSTOX_API_KEY", raising=False)
    monkeypatch.delenv("UPSTOX_API_SECRET", raising=False)
    monkeypatch.delenv("UPSTOX_REDIRECT_URI", raising=False)

    response = client.get("/api/v1/brokers/upstox/login", follow_redirects=False)
    assert response.status_code == 400


def test_login_redirects_once_credentials_saved():
    credential_store.save_credentials(
        "upstox", {"api_key": "k", "api_secret": "s", "redirect_uri": "http://x/callback"}
    )

    response = client.get("/api/v1/brokers/upstox/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert "client_id=k" in response.headers["location"]


def test_upstox_callback_success_saves_token():
    with patch(
        "backend.app.api.endpoints.brokers.upstox_auth.exchange_code_for_token",
        new=AsyncMock(return_value="live-token"),
    ), patch("backend.app.api.endpoints.brokers.upstox_auth.save_token") as mock_save:
        response = client.get("/api/v1/brokers/upstox/callback?code=abc")

    assert response.status_code == 200
    mock_save.assert_called_once_with("live-token")


def test_upstox_callback_failure_reports_error_page():
    from backend.app.core.upstox_auth import UpstoxAuthError

    with patch(
        "backend.app.api.endpoints.brokers.upstox_auth.exchange_code_for_token",
        new=AsyncMock(side_effect=UpstoxAuthError("bad code")),
    ):
        response = client.get("/api/v1/brokers/upstox/callback?code=bad")

    assert response.status_code == 502
    assert "Connection Failed" in response.text


def test_dhan_token_endpoint_validates_before_saving():
    def handler(request):
        assert request.headers["access-token"] == "tok"
        assert request.headers["dhanClientId"] == "cid"
        return httpx.Response(200, json={"availabelBalance": 1000})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    with patch(
        "backend.app.core.dhan_auth.httpx.AsyncClient",
        lambda *a, **kw: real_client(transport=transport),
    ):
        response = client.post(
            "/api/v1/brokers/dhan/token", json={"client_id": "cid", "access_token": "tok"}
        )

    assert response.status_code == 200
    assert credential_store.load_credentials("dhan")["access_token"] == "tok"


def test_dhan_token_endpoint_rejects_invalid_token_without_saving():
    def handler(request):
        return httpx.Response(401, text="Invalid token")

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    with patch(
        "backend.app.core.dhan_auth.httpx.AsyncClient",
        lambda *a, **kw: real_client(transport=transport),
    ):
        response = client.post(
            "/api/v1/brokers/dhan/token", json={"client_id": "cid", "access_token": "bad"}
        )

    assert response.status_code == 400
    assert credential_store.load_credentials("dhan") is None
