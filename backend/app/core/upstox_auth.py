import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

# Import httpx - will be monkeypatched by tests
import httpx

logger = logging.getLogger(__name__)

TOKEN_PATH = Path(__file__).resolve().parent.parent.parent / ".token.json"


class UpstoxAuthError(Exception):
    """Raised when the Upstox OAuth flow fails."""


def save_token(access_token: str) -> None:
    TOKEN_PATH.write_text(
        json.dumps(
            {
                "access_token": access_token,
                "obtained_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )


def load_token() -> Optional[str]:
    if not TOKEN_PATH.exists():
        return None
    try:
        data = json.loads(TOKEN_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return data.get("access_token")


AUTHORIZE_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"


def get_authorization_url() -> str:
    params = {
        "client_id": os.environ["UPSTOX_API_KEY"],
        "redirect_uri": os.environ["UPSTOX_REDIRECT_URI"],
        "response_type": "code",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> str:
    # Use the patched AsyncClient, which tests can intercept
    # The patched version should provide a mock transport
    async with httpx.AsyncClient() as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": os.environ["UPSTOX_API_KEY"],
                "client_secret": os.environ["UPSTOX_API_SECRET"],
                "redirect_uri": os.environ["UPSTOX_REDIRECT_URI"],
                "grant_type": "authorization_code",
            },
            headers={
                "accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

    if response.status_code != 200:
        raise UpstoxAuthError(
            f"Token exchange failed ({response.status_code}): {response.text}"
        )

    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        raise UpstoxAuthError(f"Token exchange response missing access_token: {data}")

    return access_token


