"""Static metadata describing each supported broker's credential shape.

The frontend uses this to know which form fields to render per broker
and whether connecting means "redirect through an OAuth login" or "paste
in a manually generated token." Nothing here holds actual credentials —
see credential_store for that.
"""

from dataclasses import dataclass
from typing import List, Literal

AuthType = Literal["oauth_redirect", "manual_token"]


@dataclass(frozen=True)
class CredentialField:
    name: str
    label: str
    secret: bool  # True = render as a password input, never echo back


@dataclass(frozen=True)
class BrokerDefinition:
    id: str
    display_name: str
    auth_type: AuthType
    fields: List[CredentialField]
    notes: str


BROKERS: List[BrokerDefinition] = [
    BrokerDefinition(
        id="upstox",
        display_name="Upstox",
        auth_type="oauth_redirect",
        fields=[
            CredentialField("api_key", "API Key", secret=False),
            CredentialField("api_secret", "API Secret", secret=True),
            CredentialField("redirect_uri", "Redirect URI", secret=False),
        ],
        notes="Free API. Save credentials, then click Connect to complete OAuth login.",
    ),
    BrokerDefinition(
        id="zerodha",
        display_name="Zerodha (Kite Connect)",
        auth_type="oauth_redirect",
        fields=[
            CredentialField("api_key", "API Key", secret=False),
            CredentialField("api_secret", "API Secret", secret=True),
        ],
        notes=(
            "Kite Connect requires a paid subscription (₹2000/month) from "
            "developers.kite.trade. Access token expires daily at 6 AM and must "
            "be re-connected each trading day."
        ),
    ),
    BrokerDefinition(
        id="dhan",
        display_name="Dhan",
        auth_type="manual_token",
        fields=[
            CredentialField("client_id", "Client ID", secret=False),
            CredentialField("access_token", "Access Token", secret=True),
        ],
        notes=(
            "Generate the access token from web.dhan.co → Access DhanHQ APIs. "
            "Valid for 24 hours — paste in a fresh token daily."
        ),
    ),
]

_BY_ID = {b.id: b for b in BROKERS}


def get_broker(broker_id: str) -> BrokerDefinition:
    if broker_id not in _BY_ID:
        raise KeyError(f"Unknown broker: {broker_id!r}")
    return _BY_ID[broker_id]


def is_known_broker(broker_id: str) -> bool:
    return broker_id in _BY_ID
