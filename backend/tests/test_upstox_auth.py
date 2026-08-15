import json

from backend.app.core import upstox_auth


def test_load_token_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(upstox_auth, "TOKEN_PATH", tmp_path / ".token.json")
    assert upstox_auth.load_token() is None


def test_save_then_load_token_roundtrip(tmp_path, monkeypatch):
    token_path = tmp_path / ".token.json"
    monkeypatch.setattr(upstox_auth, "TOKEN_PATH", token_path)

    upstox_auth.save_token("abc123")

    assert token_path.exists()
    saved = json.loads(token_path.read_text())
    assert saved["access_token"] == "abc123"
    assert "obtained_at" in saved

    assert upstox_auth.load_token() == "abc123"


def test_load_token_returns_none_for_malformed_file(tmp_path, monkeypatch):
    token_path = tmp_path / ".token.json"
    token_path.write_text("not valid json")
    monkeypatch.setattr(upstox_auth, "TOKEN_PATH", token_path)

    assert upstox_auth.load_token() is None
