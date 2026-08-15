# Sanate

Algo trading workstation — FastAPI backend with a live Upstox V3 market-data
feed, plus a React frontend.

## Running the backend

From the repo root:

```bash
.venv/Scripts/python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

Health check: http://localhost:8000/api/health

## Upstox setup

The live market-data feed needs a real Upstox OAuth access token. Without one
the backend still starts, but stays in mock mode (it logs a warning instead of
connecting to the feed).

1. Create an app in the [Upstox developer console](https://account.upstox.com/developer/apps)
   and set its redirect URI to
   `http://localhost:8000/api/v1/broker/upstox/callback`.

2. Copy the example env file and fill in your credentials:

   ```bash
   cp backend/.env.example backend/.env
   ```

   ```
   UPSTOX_API_KEY=<your app's API key>
   UPSTOX_API_SECRET=<your app's API secret>
   UPSTOX_REDIRECT_URI=http://localhost:8000/api/v1/broker/upstox/callback
   ```

   `backend/.env` must live in `backend/`, not the repo root — `main.py` loads
   it by explicit path. It is gitignored; never commit real credentials.

3. Start the backend, then visit
   http://localhost:8000/api/v1/broker/upstox/login in a browser. That
   redirects you to Upstox to log in; on success the callback saves the token
   to `backend/.token.json` and connects the live feed.

Upstox access tokens expire daily. On startup the backend reuses a saved token
if one exists; once it expires, just hit `/api/v1/broker/upstox/login` again.

## Tests

```bash
.venv/Scripts/python.exe -m pytest -q --timeout=60
```

Always pass `--timeout=60` — some tests construct a `TestClient` over the full
app, and a regression there can hang the run rather than fail it.
