import json

import httpx
import pytest

from backend.app.core import upstox_auth


def test_load_token_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(upstox_auth, "TOKEN_PATH", tmp_path / ".token.json")
    assert upstox_auth.load_token() is None


def test_save_then_load_token_roundtrip(tmp_path, monkeypatch):
    token_path = tmp_path / ".token.json"
    monkeypatch.setattr(upstox_auth, "TOKEN_PATH", token_path)

    upstox_auth.save_token("abc123")

    assert token_path.exists()
    saved = json.loads(token_path.read_text())
    assert saved["access_token"] == "abc123"
    assert "obtained_at" in saved

    assert upstox_auth.load_token() == "abc123"


def test_load_token_returns_none_for_malformed_file(tmp_path, monkeypatch):
    token_path = tmp_path / ".token.json"
    token_path.write_text("not valid json")
    monkeypatch.setattr(upstox_auth, "TOKEN_PATH", token_path)

    assert upstox_auth.load_token() is None


def test_get_authorization_url_uses_env_vars(monkeypatch):
    monkeypatch.setenv("UPSTOX_API_KEY", "my-client-id")
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")

    url = upstox_auth.get_authorization_url()

    assert url.startswith("https://api.upstox.com/v2/login/authorization/dialog?")
    assert "client_id=my-client-id" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fcallback" in url
    assert "response_type=code" in url


@pytest.mark.asyncio
async def test_exchange_code_for_token_success(monkeypatch):
    monkeypatch.setenv("UPSTOX_API_KEY", "my-client-id")
    monkeypatch.setenv("UPSTOX_API_SECRET", "my-secret")
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")

    def handler(request):
        assert request.url.path == "/v2/login/authorization/token"
        return httpx.Response(200, json={"access_token": "live-token-xyz"})

    transport = httpx.MockTransport(handler)
    original_async_client = upstox_auth.httpx.AsyncClient

    monkeypatch.setattr(
        upstox_auth.httpx, "AsyncClient", lambda *a, **kw: original_async_client(transport=transport)
    )

    token = await upstox_auth.exchange_code_for_token("auth-code-123")

    assert token == "live-token-xyz"


@pytest.mark.asyncio
async def test_exchange_code_for_token_failure_raises(monkeypatch):
    monkeypatch.setenv("UPSTOX_API_KEY", "my-client-id")
    monkeypatch.setenv("UPSTOX_API_SECRET", "my-secret")
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")

    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    transport = httpx.MockTransport(handler)
    original_async_client = upstox_auth.httpx.AsyncClient
    monkeypatch.setattr(
        upstox_auth.httpx, "AsyncClient", lambda *a, **kw: original_async_client(transport=transport)
    )

    with pytest.raises(upstox_auth.UpstoxAuthError):
        await upstox_auth.exchange_code_for_token("bad-code")
