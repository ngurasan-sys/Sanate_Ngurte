"""Zerodha Kite Connect OAuth flow.

Kite Connect requires a paid API subscription (developers.kite.trade) —
this module doesn't change that, it just wires up the real login/token
exchange once a user has their own subscribed app credentials.

Flow: redirect to Kite's login page -> user logs in with their Zerodha
credentials & 2FA -> Kite redirects back with a request_token -> exchange
that (plus a SHA-256 checksum of api_key+request_token+api_secret) for an
access_token. The access token expires daily at 6 AM IST — there is no
silent refresh; the user must reconnect each trading day.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

from backend.app.core import credential_store

logger = logging.getLogger(__name__)

LOGIN_URL = "https://kite.zerodha.com/connect/login"
TOKEN_URL = "https://api.kite.trade/session/token"


class ZerodhaAuthError(Exception):
    """Raised when the Zerodha Kite Connect OAuth flow fails."""


def _require_credential(field: str) -> str:
    stored = credential_store.load_credentials("zerodha")
    value = stored.get(field) if stored else None
    if not value:
        raise ZerodhaAuthError(
            f"Zerodha {field} not set — save your Kite Connect API key and "
            "secret via the Broker Connections page"
        )
    return value


def get_authorization_url() -> str:
    api_key = _require_credential("api_key")
    params = {"v": "3", "api_key": api_key}
    return f"{LOGIN_URL}?{urlencode(params)}"


async def exchange_request_token(request_token: str) -> str:
    api_key = _require_credential("api_key")
    api_secret = _require_credential("api_secret")

    checksum = hashlib.sha256(
        (api_key + request_token + api_secret).encode("utf-8")
    ).hexdigest()

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "api_key": api_key,
                    "request_token": request_token,
                    "checksum": checksum,
                },
                headers={"X-Kite-Version": "3"},
            )
    except httpx.HTTPError as exc:
        raise ZerodhaAuthError(f"Token exchange request failed: {exc}")

    if response.status_code != 200:
        raise ZerodhaAuthError(
            f"Token exchange failed ({response.status_code}): {response.text}"
        )

    data = response.json().get("data", {})
    access_token = data.get("access_token")
    if not access_token:
        raise ZerodhaAuthError(f"Token exchange response missing access_token: {data}")

    return access_token


def save_token(access_token: str) -> None:
    stored = credential_store.load_credentials("zerodha") or {}
    stored["access_token"] = access_token
    stored["token_obtained_at"] = datetime.now(timezone.utc).isoformat()
    credential_store.save_credentials("zerodha", stored)


def load_token() -> Optional[str]:
    stored = credential_store.load_credentials("zerodha")
    return stored.get("access_token") if stored else None
