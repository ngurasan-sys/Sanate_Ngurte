# Starts backend (uvicorn) and frontend (vite) each in their own window.
# Usage: ./dev.ps1

$root = $PSScriptRoot

Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "cd '$root'; `$env:PYTHONPATH='.'; .venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000"
) -WorkingDirectory $root

Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command',
    "cd '$root\frontend'; npm run dev"
) -WorkingDirectory "$root\frontend"

Write-Host "Backend starting on http://localhost:8000 (new window)"
Write-Host "Frontend starting on http://localhost:5173 (new window)"
