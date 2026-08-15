import pytest

from backend.app.core import credential_store


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setattr(credential_store, "STORE_PATH", tmp_path / ".broker_credentials.json")
    monkeypatch.setattr(credential_store, "KEY_PATH", tmp_path / ".credential_key")


def test_load_returns_none_when_nothing_saved():
    assert credential_store.load_credentials("upstox") is None


def test_save_then_load_roundtrip():
    credential_store.save_credentials("upstox", {"api_key": "abc", "api_secret": "xyz"})

    loaded = credential_store.load_credentials("upstox")

    assert loaded == {"api_key": "abc", "api_secret": "xyz"}


def test_file_on_disk_is_encrypted_not_plaintext():
    credential_store.save_credentials("upstox", {"api_secret": "super-secret-value"})

    raw = credential_store.STORE_PATH.read_text(encoding="utf-8")

    assert "super-secret-value" not in raw


def test_separate_brokers_stored_independently():
    credential_store.save_credentials("upstox", {"api_key": "up-key"})
    credential_store.save_credentials("dhan", {"client_id": "dhan-id"})

    assert credential_store.load_credentials("upstox") == {"api_key": "up-key"}
    assert credential_store.load_credentials("dhan") == {"client_id": "dhan-id"}


def test_save_overwrites_previous_value_for_same_broker():
    credential_store.save_credentials("upstox", {"api_key": "first"})
    credential_store.save_credentials("upstox", {"api_key": "second"})

    assert credential_store.load_credentials("upstox") == {"api_key": "second"}


def test_delete_removes_only_that_broker():
    credential_store.save_credentials("upstox", {"api_key": "up-key"})
    credential_store.save_credentials("dhan", {"client_id": "dhan-id"})

    credential_store.delete_credentials("upstox")

    assert credential_store.load_credentials("upstox") is None
    assert credential_store.load_credentials("dhan") == {"client_id": "dhan-id"}


def test_delete_of_unknown_broker_is_a_no_op():
    credential_store.delete_credentials("nonexistent")  # must not raise


def test_list_connected_brokers():
    assert credential_store.list_connected_brokers() == []

    credential_store.save_credentials("upstox", {"api_key": "x"})
    credential_store.save_credentials("dhan", {"client_id": "y"})

    assert sorted(credential_store.list_connected_brokers()) == ["dhan", "upstox"]


def test_load_with_corrupted_ciphertext_returns_none_instead_of_raising():
    credential_store.save_credentials("upstox", {"api_key": "abc"})
    # Simulate the key file changing after data was written (e.g. a fresh
    # key generated on a different machine) — decryption must fail closed.
    credential_store.KEY_PATH.unlink()

    assert credential_store.load_credentials("upstox") is None
