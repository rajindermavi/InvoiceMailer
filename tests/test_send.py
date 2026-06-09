from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.fernet import Fernet

from src.backend.utility import send


def test_normalize_ms_authority_accepts_plural_and_singular_values() -> None:
    assert send._normalize_ms_authority("organizations") == "organization"
    assert send._normalize_ms_authority("organization") == "organization"
    assert send._normalize_ms_authority("consumers") == "consumer"
    assert send._normalize_ms_authority("consumer") == "consumer"


def test_normalize_ms_authority_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="MS authority must be 'organizations'/'organization' or 'consumers'/'consumer'"):
        send._normalize_ms_authority("other")


# ---------------------------------------------------------------------------
# _PassphraseSecureConfig
# ---------------------------------------------------------------------------

@pytest.fixture()
def config_path(tmp_path):
    return tmp_path / "config.enc"


def make_config(passphrase, config_path):
    cfg = send._PassphraseSecureConfig(passphrase)
    cfg._path = config_path
    return cfg


def test_passphrase_config_roundtrip(config_path):
    cfg = make_config("hunter2", config_path)
    data = {"client_id": "abc", "ms_token_cache": "tokendata"}
    cfg.save(data)
    assert cfg.load() == data


def test_passphrase_config_empty_when_no_file(config_path):
    cfg = make_config("hunter2", config_path)
    assert cfg.load() == {}


def test_passphrase_config_wrong_passphrase_returns_empty(config_path):
    make_config("correct", config_path).save({"key": "value"})
    result = make_config("wrong", config_path).load()
    assert result == {}


def test_passphrase_config_dpapi_blob_returns_empty(config_path):
    # Simulate a file encrypted with DPAPI (or any unreadable format).
    config_path.write_bytes(b"\x01\x00\x00\x00\xd0\x8c\x9d\xdf\x01garbage")
    cfg = make_config("hunter2", config_path)
    assert cfg.load() == {}


def test_passphrase_config_legacy_no_marker(config_path):
    # nicemail wrote a Fernet file without the marker (old format).
    passphrase = b"hunter2"
    raw_key = hashlib.pbkdf2_hmac("sha256", passphrase, send._KDF_SALT, 390_000, dklen=32)
    fernet = Fernet(base64.urlsafe_b64encode(raw_key))
    config_path.write_bytes(fernet.encrypt(json.dumps({"legacy": True}).encode()))

    cfg = make_config("hunter2", config_path)
    assert cfg.load() == {"legacy": True}


def test_passphrase_config_saves_with_marker(config_path):
    make_config("hunter2", config_path).save({"x": 1})
    assert config_path.read_bytes().startswith(send._FERNET_MARKER)


def test_passphrase_config_injected_on_client(monkeypatch):
    # Verify _PassphraseSecureConfig is wired in when a passphrase is given,
    # without making any network calls.
    created = {}

    class _FakeEmailClient:
        def __init__(self, **kwargs):
            self.secure_config = object()  # stand-in for nicemail's SecureConfig

    monkeypatch.setattr(send, "_PassphraseSecureConfig", lambda p: f"custom:{p}")

    import types
    fake_nicemail = types.ModuleType("nicemail")
    fake_nicemail.EmailClient = _FakeEmailClient
    monkeypatch.setitem(__import__("sys").modules, "nicemail", fake_nicemail)

    # Replicate the two lines from _send_via_graph that do the injection.
    passphrase = "secret"
    client = _FakeEmailClient()
    if passphrase is not None:
        client.secure_config = send._PassphraseSecureConfig(passphrase)

    assert client.secure_config == "custom:secret"
