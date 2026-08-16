"""Unified multi-broker credential + connection API.

Lets the frontend show a broker picker (Upstox / Zerodha / Dhan), render
the right credential form per broker, and drive each broker's real auth
flow — OAuth redirect for Upstox/Zerodha, paste-in-a-token for Dhan.

Scope note: this only manages credentials and connection status. Live
market data and order placement still run exclusively through Upstox
(see backend.app.execution.order_gateway and backend.app.market_data) —
wiring Zerodha/Dhan into the actual trading engines is a separate,
larger project.

Secrets are never echoed back to the frontend: status responses report
only whether a broker is connected, not the stored key/secret/token
values.
"""

import html
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from backend.app.core import credential_store, dhan_auth, upstox_auth, zerodha_auth
from backend.app.core.active_broker import BrokerSwitchError, active_broker
from backend.app.core.broker_registry import BROKERS, get_broker, is_known_broker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/brokers", tags=["brokers"])


class SaveCredentialsRequest(BaseModel):
    fields: dict


class DhanTokenRequest(BaseModel):
    client_id: str
    access_token: str


class SetActiveBrokerRequest(BaseModel):
    broker_id: str


def _result_page(broker_id: str, status: str, detail: str = "") -> str:
    is_error = status == "ERROR"
    heading = "Connection Failed" if is_error else "Connected"
    color = "#ef4444" if is_error else "#10b981"
    body_text = html.escape(detail or "Authentication successful. You can close this window.")
    close_delay_ms = "3000" if is_error else "1000"

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{heading}</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background: #09090b; color: {color}; margin: 0; }}
            .container {{ text-align: center; border: 1px solid #27272a; padding: 2rem; border-radius: 8px; background: #18181b; max-width: 480px; }}
            h1 {{ margin-bottom: 1rem; font-size: 1.5rem; text-transform: uppercase; letter-spacing: 0.05em; }}
            p {{ color: #a1a1aa; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{heading}</h1>
            <p>{body_text}</p>
        </div>
        <script>
            if (window.opener) {{
                window.opener.postMessage({{
                    type: "BROKER_AUTH_COMPLETE",
                    broker: "{broker_id.upper()}",
                    status: "{status}"
                }}, window.location.origin);
            }}
            setTimeout(() => {{ window.close(); }}, {close_delay_ms});
        </script>
    </body>
    </html>
    """


def _require_known_broker(broker_id: str) -> None:
    if not is_known_broker(broker_id):
        raise HTTPException(status_code=404, detail=f"Unknown broker: {broker_id!r}")


def _is_connected(broker_id: str) -> bool:
    if broker_id == "upstox":
        return upstox_auth.load_token() is not None
    if broker_id == "zerodha":
        return zerodha_auth.load_token() is not None
    if broker_id == "dhan":
        return dhan_auth.load_token() is not None
    return False


@router.get("")
async def list_brokers():
    return [
        {
            "id": b.id,
            "display_name": b.display_name,
            "auth_type": b.auth_type,
            "fields": [
                {"name": f.name, "label": f.label, "secret": f.secret} for f in b.fields
            ],
            "notes": b.notes,
            "connected": _is_connected(b.id),
        }
        for b in BROKERS
    ]


@router.get("/active")
async def get_active_broker():
    return {"broker_id": active_broker.get_active_broker_id()}


@router.post("/active")
async def set_active_broker(req: SetActiveBrokerRequest):
    try:
        await active_broker.set_active_broker(req.broker_id)
    except BrokerSwitchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"broker_id": req.broker_id, "active": True}


@router.get("/{broker_id}/status")
async def broker_status(broker_id: str):
    _require_known_broker(broker_id)
    stored = credential_store.load_credentials(broker_id)
    return {
        "broker_id": broker_id,
        "credentials_saved": stored is not None,
        "connected": _is_connected(broker_id),
    }


@router.post("/{broker_id}/credentials")
async def save_credentials(broker_id: str, req: SaveCredentialsRequest):
    """Save app-level credentials (api_key/api_secret/redirect_uri) for an
    oauth_redirect broker. Does not itself connect — call .../login next.
    Dhan uses POST .../dhan/token instead (validated immediately)."""
    _require_known_broker(broker_id)
    broker = get_broker(broker_id)
    if broker.auth_type != "oauth_redirect":
        raise HTTPException(
            status_code=400,
            detail=f"{broker.display_name} uses a different connection flow — see /dhan/token.",
        )

    known_fields = {f.name for f in broker.fields}
    unknown = set(req.fields) - known_fields
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown fields for {broker_id}: {unknown}")

    missing = known_fields - set(req.fields)
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {missing}")

    credential_store.save_credentials(broker_id, req.fields)
    return {"broker_id": broker_id, "saved": True}


@router.delete("/{broker_id}/credentials")
async def delete_credentials(broker_id: str):
    _require_known_broker(broker_id)
    credential_store.delete_credentials(broker_id)
    return {"broker_id": broker_id, "saved": False, "connected": False}


@router.get("/{broker_id}/login")
async def broker_login(broker_id: str):
    _require_known_broker(broker_id)
    broker = get_broker(broker_id)
    if broker.auth_type != "oauth_redirect":
        raise HTTPException(status_code=400, detail=f"{broker.display_name} has no login redirect.")

    try:
        if broker_id == "upstox":
            url = upstox_auth.get_authorization_url()
        elif broker_id == "zerodha":
            url = zerodha_auth.get_authorization_url()
        else:
            raise HTTPException(status_code=400, detail="No login handler for this broker.")
    except (upstox_auth.UpstoxAuthError, zerodha_auth.ZerodhaAuthError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=url)


@router.get("/upstox/callback")
async def upstox_callback(code: str, state: str | None = None):
    try:
        token = await upstox_auth.exchange_code_for_token(code)
        upstox_auth.save_token(token)
    except upstox_auth.UpstoxAuthError as exc:
        logger.error("Upstox token exchange failed: %s", exc)
        return HTMLResponse(content=_result_page("upstox", "ERROR", str(exc)), status_code=502)
    return HTMLResponse(content=_result_page("upstox", "CONNECTED"))


@router.get("/zerodha/callback")
async def zerodha_callback(request_token: str, status: str | None = None):
    if status == "cancelled":
        return HTMLResponse(
            content=_result_page("zerodha", "ERROR", "Login was cancelled."), status_code=200
        )
    try:
        token = await zerodha_auth.exchange_request_token(request_token)
        zerodha_auth.save_token(token)
    except zerodha_auth.ZerodhaAuthError as exc:
        logger.error("Zerodha token exchange failed: %s", exc)
        return HTMLResponse(content=_result_page("zerodha", "ERROR", str(exc)), status_code=502)
    return HTMLResponse(content=_result_page("zerodha", "CONNECTED"))


@router.post("/dhan/token")
async def dhan_save_token(req: DhanTokenRequest):
    try:
        await dhan_auth.validate_and_save_token(req.client_id, req.access_token)
    except dhan_auth.DhanAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"broker_id": "dhan", "connected": True}
