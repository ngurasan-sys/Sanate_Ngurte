from unittest.mock import patch

from fastapi.testclient import TestClient


def test_startup_starts_and_shutdown_stops_expiry_reversal_engine():
    with patch("backend.app.main.expiry_reversal_engine") as mock_engine:
        from backend.app.main import app

        with TestClient(app):
            mock_engine.start.assert_called_once()

        mock_engine.stop.assert_called_once()
