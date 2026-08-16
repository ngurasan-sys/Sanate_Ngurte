import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx

from backend.app.core import credential_store

logger = logging.getLogger(__name__)

TOKEN_PATH = Path(__file__).resolve().parent.parent.parent / ".token.json"


class UpstoxAuthError(Exception):
    """Raised when the Upstox OAuth flow fails."""


def _require_credential(field: str, env_name: str) -> str:
    """Resolve a required Upstox app credential (api_key/api_secret/
    redirect_uri), preferring credentials saved via the frontend's Broker
    Connections page and falling back to backend/.env for the original
    setup path. Fails with a clear, actionable message either way."""
    stored = credential_store.load_credentials("upstox")
    if stored and stored.get(field):
        return stored[field]

    value = os.environ.get(env_name)
    if value is None:
        raise UpstoxAuthError(
            f"{env_name} not set — copy backend/.env.example to backend/.env "
            "and fill in your credentials, or save Upstox credentials via the "
            "Broker Connections page"
        )
    return value


def save_token(access_token: str) -> None:
    TOKEN_PATH.write_text(
        json.dumps(
            {
                "access_token": access_token,
                "obtained_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )


def load_token() -> Optional[str]:
    if not TOKEN_PATH.exists():
        return None
    try:
        data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data.get("access_token")


def has_any_usable_token() -> bool:
    """True when Upstox can actually place *some* order — either the live
    OAuth token is saved, or a sandbox-only token is configured via
    UPSTOX_SANDBOX_ACCESS_TOKEN.

    Readiness must not be gated purely on load_token(): SANDBOX mode uses
    a separate token (see execution/upstox_adapter._resolve_token) that is
    obtainable without ever running the OAuth login. Gating on load_token()
    alone would leave a fully-configured EXECUTION_MODE=SANDBOX developer
    setup with no active broker, silently REJECTing every order.
    """
    if load_token() is not None:
        return True
    return bool(os.environ.get("UPSTOX_SANDBOX_ACCESS_TOKEN"))


AUTHORIZE_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"


def get_authorization_url() -> str:
    params = {
        "client_id": _require_credential("api_key", "UPSTOX_API_KEY"),
        "redirect_uri": _require_credential("redirect_uri", "UPSTOX_REDIRECT_URI"),
        "response_type": "code",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> str:
    client_id = _require_credential("api_key", "UPSTOX_API_KEY")
    client_secret = _require_credential("api_secret", "UPSTOX_API_SECRET")
    redirect_uri = _require_credential("redirect_uri", "UPSTOX_REDIRECT_URI")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={
                    "accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
    except httpx.HTTPError as exc:
        raise UpstoxAuthError(f"Token exchange request failed: {exc}")

    if response.status_code != 200:
        raise UpstoxAuthError(
            f"Token exchange failed ({response.status_code}): {response.text}"
        )

    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        raise UpstoxAuthError(f"Token exchange response missing access_token: {data}")

    return access_token
