import logging
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/broker/upstox", tags=["broker"])

@router.get("/login")
async def upstox_login():
    # Simulate redirecting to Upstox OAuth
    # In a real app, this would be https://api.upstox.com/v2/login/authorization/dialog?...
    # Here, we will redirect directly to our callback with a mock code to simulate the flow
    return RedirectResponse(url="/api/v1/broker/upstox/callback?code=mock_auth_code_12345&state=somerandomstate")

@router.get("/callback")
async def upstox_callback(code: str = Query(...), state: str = Query(None)):
    logger.info(f"Received Upstox callback with code: {code}")

    # In a real app, exchange code for access token here, and securely store it
    # token_data = exchange_code(code)
    # store_token(token_data)

    # Render HTML page to postMessage back to original window
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Upstox Connected</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; background: #09090b; color: #10b981; margin: 0; }
            .container { text-align: center; border: 1px solid #27272a; padding: 2rem; border-radius: 8px; background: #18181b; }
            h1 { margin-bottom: 1rem; font-size: 1.5rem; text-transform: uppercase; letter-spacing: 0.05em; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Upstox Connected</h1>
            <p>Authentication successful. You can close this window.</p>
        </div>
        <script>
            // Safely notify the opener window
            if (window.opener) {
                const message = {
                    type: "BROKER_AUTH_COMPLETE",
                    broker: "UPSTOX",
                    status: "CONNECTED"
                };
                window.opener.postMessage(message, window.location.origin);
            } else {
                console.warn("No opener window found.");
            }

            // Attempt to auto-close
            setTimeout(() => {
                window.close();
            }, 1000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
