import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
