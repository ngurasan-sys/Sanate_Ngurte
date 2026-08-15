from unittest.mock import patch

import httpx
import pytest

from backend.app.core import credential_store, zerodha_auth


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setattr(credential_store, "STORE_PATH", tmp_path / ".broker_credentials.json")
    monkeypatch.setattr(credential_store, "KEY_PATH", tmp_path / ".credential_key")


def test_get_authorization_url_raises_when_no_credentials_saved():
    with pytest.raises(zerodha_auth.ZerodhaAuthError):
        zerodha_auth.get_authorization_url()


def test_get_authorization_url_uses_saved_api_key():
    credential_store.save_credentials("zerodha", {"api_key": "my-key", "api_secret": "s"})

    url = zerodha_auth.get_authorization_url()

    assert url == "https://kite.zerodha.com/connect/login?v=3&api_key=my-key"


@pytest.mark.asyncio
async def test_exchange_request_token_computes_checksum_and_returns_token():
    credential_store.save_credentials("zerodha", {"api_key": "key1", "api_secret": "secret1"})

    captured = {}

    def handler(request):
        body = request.content.decode()
        captured["body"] = body
        return httpx.Response(200, json={"data": {"access_token": "zerodha-token-abc"}})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    with patch(
        "backend.app.core.zerodha_auth.httpx.AsyncClient",
        lambda *a, **kw: real_client(transport=transport),
    ):
        token = await zerodha_auth.exchange_request_token("req-token-xyz")

    assert token == "zerodha-token-abc"
    assert "request_token=req-token-xyz" in captured["body"]
    assert "checksum=" in captured["body"]


@pytest.mark.asyncio
async def test_exchange_request_token_failure_raises():
    credential_store.save_credentials("zerodha", {"api_key": "key1", "api_secret": "secret1"})

    def handler(request):
        return httpx.Response(403, json={"error_type": "TokenException"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    with patch(
        "backend.app.core.zerodha_auth.httpx.AsyncClient",
        lambda *a, **kw: real_client(transport=transport),
    ):
        with pytest.raises(zerodha_auth.ZerodhaAuthError):
            await zerodha_auth.exchange_request_token("bad-token")


def test_save_and_load_token_roundtrip():
    credential_store.save_credentials("zerodha", {"api_key": "k", "api_secret": "s"})

    zerodha_auth.save_token("access-abc")

    assert zerodha_auth.load_token() == "access-abc"
    # api_key/api_secret must survive the token being layered on top
    assert credential_store.load_credentials("zerodha")["api_key"] == "k"


def test_load_token_returns_none_when_nothing_saved():
    assert zerodha_auth.load_token() is None
