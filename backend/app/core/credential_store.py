"""Encrypted local storage for user-supplied broker credentials.

Users enter API keys/secrets/tokens for their chosen brokerage(s) through
the frontend; this module is where those values land at rest. Same
single-machine trust model as the pre-existing backend/.token.json (this
is a self-hosted personal trading workstation, not a multi-tenant
service) — but encrypted, since this file holds broker API secrets and
live access tokens rather than just one derived Upstox token.

The encryption key is generated once on first use and written to
backend/.credential_key (gitignored, like .token.json). Losing that file
means every stored credential must be re-entered — there is no recovery
path, by design, since we never want a second copy of the key anywhere.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
KEY_PATH = _BACKEND_ROOT / ".credential_key"
STORE_PATH = _BACKEND_ROOT / ".broker_credentials.json"


def _load_or_create_key() -> bytes:
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    logger.info("Generated a new broker-credential encryption key at %s", KEY_PATH)
    return key


def _fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def _read_store() -> Dict[str, str]:
    if not STORE_PATH.exists():
        return {}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_store(data: Dict[str, str]) -> None:
    STORE_PATH.write_text(json.dumps(data), encoding="utf-8")


def save_credentials(broker: str, data: Dict[str, Any]) -> None:
    """Encrypt and persist a broker's credential fields, replacing
    whatever was stored for that broker before."""
    payload = json.dumps(data).encode("utf-8")
    encrypted = _fernet().encrypt(payload)

    store = _read_store()
    store[broker] = encrypted.decode("utf-8")
    _write_store(store)


def load_credentials(broker: str) -> Optional[Dict[str, Any]]:
    store = _read_store()
    raw = store.get(broker)
    if raw is None:
        return None
    try:
        decrypted = _fernet().decrypt(raw.encode("utf-8"))
    except InvalidToken:
        logger.error(
            "Stored credentials for %r could not be decrypted — the key file "
            "may have changed. Treating as not connected.", broker,
        )
        return None
    return json.loads(decrypted.decode("utf-8"))


def delete_credentials(broker: str) -> None:
    store = _read_store()
    if broker in store:
        del store[broker]
        _write_store(store)


def list_connected_brokers() -> List[str]:
    return list(_read_store().keys())
