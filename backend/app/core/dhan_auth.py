"""Dhan credential handling.

Individual Dhan traders don't go through a redirect OAuth flow: they log
into web.dhan.co, generate an access token from "Access DhanHQ APIs", and
paste that token (plus their client ID) in directly. The token is a JWT
valid for 24 hours with no refresh — it has to be pasted in fresh daily.

Because there's no redirect flow to prove the credentials work, we
validate a freshly-entered token against a real Dhan endpoint before
ever reporting the connection as successful — never fabricate a
"connected" status.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from backend.app.core import credential_store

logger = logging.getLogger(__name__)

FUND_LIMIT_URL = "https://api.dhan.co/v2/fundlimit"


class DhanAuthError(Exception):
    """Raised when a Dhan access token can't be validated or is missing."""


async def validate_and_save_token(client_id: str, access_token: str) -> None:
    """Confirm the token actually works against Dhan's API before saving
    it as the active credential — a token that merely looks well-formed
    is not the same as one Dhan will accept."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                FUND_LIMIT_URL,
                headers={"access-token": access_token, "dhanClientId": client_id},
            )
    except httpx.HTTPError as exc:
        raise DhanAuthError(f"Could not reach Dhan to validate the token: {exc}")

    if response.status_code != 200:
        raise DhanAuthError(
            f"Dhan rejected this client ID / access token ({response.status_code}): "
            f"{response.text}"
        )

    credential_store.save_credentials(
        "dhan",
        {
            "client_id": client_id,
            "access_token": access_token,
            "token_obtained_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def load_token() -> Optional[str]:
    stored = credential_store.load_credentials("dhan")
    return stored.get("access_token") if stored else None


def load_client_id() -> Optional[str]:
    stored = credential_store.load_credentials("dhan")
    return stored.get("client_id") if stored else None
