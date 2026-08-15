from unittest.mock import patch

import httpx
import pytest

from backend.app.core import credential_store, dhan_auth


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setattr(credential_store, "STORE_PATH", tmp_path / ".broker_credentials.json")
    monkeypatch.setattr(credential_store, "KEY_PATH", tmp_path / ".credential_key")


@pytest.mark.asyncio
async def test_validate_and_save_token_saves_on_success():
    def handler(request):
        return httpx.Response(200, json={"availabelBalance": 5000})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    with patch(
        "backend.app.core.dhan_auth.httpx.AsyncClient",
        lambda *a, **kw: real_client(transport=transport),
    ):
        await dhan_auth.validate_and_save_token("client-1", "token-1")

    assert dhan_auth.load_token() == "token-1"
    assert dhan_auth.load_client_id() == "client-1"


@pytest.mark.asyncio
async def test_validate_and_save_token_does_not_save_on_rejection():
    def handler(request):
        return httpx.Response(401, text="Invalid Access Token")

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    with patch(
        "backend.app.core.dhan_auth.httpx.AsyncClient",
        lambda *a, **kw: real_client(transport=transport),
    ):
        with pytest.raises(dhan_auth.DhanAuthError):
            await dhan_auth.validate_and_save_token("client-1", "bad-token")

    assert dhan_auth.load_token() is None


@pytest.mark.asyncio
async def test_validate_and_save_token_wraps_transport_failure():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    with patch(
        "backend.app.core.dhan_auth.httpx.AsyncClient",
        lambda *a, **kw: real_client(transport=transport),
    ):
        with pytest.raises(dhan_auth.DhanAuthError):
            await dhan_auth.validate_and_save_token("client-1", "token-1")

    assert dhan_auth.load_token() is None


def test_load_token_and_client_id_return_none_when_nothing_saved():
    assert dhan_auth.load_token() is None
    assert dhan_auth.load_client_id() is None
