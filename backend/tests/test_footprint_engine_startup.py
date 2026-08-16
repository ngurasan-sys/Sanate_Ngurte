from unittest.mock import patch

from fastapi.testclient import TestClient


def test_startup_starts_and_shutdown_stops_footprint_processor_and_mock_feed():
    with patch("backend.app.main.footprint_processor") as mock_processor, \
         patch("backend.app.main.mock_footprint_feed") as mock_feed:
        from backend.app.main import app

        with TestClient(app):
            mock_processor.start.assert_called_once()
            mock_feed.start.assert_called_once()

        mock_processor.stop.assert_called_once()
        mock_feed.stop.assert_called_once()
