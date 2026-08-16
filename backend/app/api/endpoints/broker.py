import html
import logging
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.app.core import upstox_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/broker/upstox", tags=["broker"])


def _result_page(status: str, detail: str = "") -> str:
    is_error = status == "ERROR"
    heading = "Upstox Connection Failed" if is_error else "Upstox Connected"
    color = "#ef4444" if is_error else "#10b981"
    body_text = html.escape(
        detail or "Authentication successful. You can close this window."
    )
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
                const message = {{
                    type: "BROKER_AUTH_COMPLETE",
                    broker: "UPSTOX",
                    status: "{status}"
                }};
                window.opener.postMessage(message, window.location.origin);
            }} else {{
                console.warn("No opener window found.");
            }}
            setTimeout(() => {{ window.close(); }}, {close_delay_ms});
        </script>
    </body>
    </html>
    """


@router.get("/login")
async def upstox_login():
    return RedirectResponse(url=upstox_auth.get_authorization_url())


@router.get("/callback")
async def upstox_callback(code: str = Query(...), state: str = Query(None)):
    logger.info("Received Upstox callback")

    try:
        token = await upstox_auth.exchange_code_for_token(code)
        upstox_auth.save_token(token)
    except upstox_auth.UpstoxAuthError as exc:
        logger.error(f"Upstox token exchange failed: {exc}")
        return HTMLResponse(content=_result_page("ERROR", str(exc)), status_code=502)
    except Exception:
        # Anything else (token file write, SDK construction, socket setup) is
        # an internal failure — log the detail, don't leak it to the browser.
        logger.exception("Upstox connection setup failed")
        return HTMLResponse(
            content=_result_page(
                "ERROR", "Failed to complete Upstox connection setup"
            ),
            status_code=500,
        )

    return HTMLResponse(content=_result_page("CONNECTED"))
