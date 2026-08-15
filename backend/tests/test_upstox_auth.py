import json

import httpx
import pytest

from backend.app.core import credential_store, upstox_auth


@pytest.fixture(autouse=True)
def _isolate_credential_store(tmp_path, monkeypatch):
    # These tests assert on env-var fallback behaviour; point the store at
    # an empty tmp path so a real backend/.broker_credentials.json (e.g.
    # from manual testing on this machine) can never leak in and short
    # -circuit the env-var resolution these tests are checking.
    monkeypatch.setattr(credential_store, "STORE_PATH", tmp_path / ".broker_credentials.json")
    monkeypatch.setattr(credential_store, "KEY_PATH", tmp_path / ".credential_key")


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


def test_get_authorization_url_raises_clear_error_when_env_missing(monkeypatch):
    monkeypatch.delenv("UPSTOX_API_KEY", raising=False)
    monkeypatch.delenv("UPSTOX_REDIRECT_URI", raising=False)

    with pytest.raises(upstox_auth.UpstoxAuthError) as excinfo:
        upstox_auth.get_authorization_url()

    assert "UPSTOX_API_KEY not set" in str(excinfo.value)
    assert "backend/.env" in str(excinfo.value)


@pytest.mark.asyncio
async def test_exchange_code_for_token_raises_clear_error_when_env_missing(monkeypatch):
    monkeypatch.delenv("UPSTOX_API_KEY", raising=False)
    monkeypatch.delenv("UPSTOX_API_SECRET", raising=False)
    monkeypatch.delenv("UPSTOX_REDIRECT_URI", raising=False)

    with pytest.raises(upstox_auth.UpstoxAuthError) as excinfo:
        await upstox_auth.exchange_code_for_token("some-code")

    assert "UPSTOX_API_KEY not set" in str(excinfo.value)


def test_get_authorization_url_prefers_stored_credentials_over_env(monkeypatch):
    monkeypatch.setenv("UPSTOX_API_KEY", "env-client-id")
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/env-callback")
    credential_store.save_credentials(
        "upstox", {"api_key": "stored-client-id", "redirect_uri": "http://localhost:8000/stored-callback"}
    )

    url = upstox_auth.get_authorization_url()

    assert "client_id=stored-client-id" in url
    assert "client_id=env-client-id" not in url


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


@pytest.mark.asyncio
async def test_exchange_code_for_token_transport_error_wrapped(monkeypatch):
    monkeypatch.setenv("UPSTOX_API_KEY", "my-client-id")
    monkeypatch.setenv("UPSTOX_API_SECRET", "my-secret")
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/callback")

    def handler(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    original_async_client = upstox_auth.httpx.AsyncClient
    monkeypatch.setattr(
        upstox_auth.httpx, "AsyncClient", lambda *a, **kw: original_async_client(transport=transport)
    )

    with pytest.raises(upstox_auth.UpstoxAuthError):
        await upstox_auth.exchange_code_for_token("auth-code-123")
