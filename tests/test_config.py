from __future__ import annotations

import backend.config as config


def test_get_storage_dir_uses_cwd_in_development(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.chdir(tmp_path)

    assert config.get_storage_dir() == tmp_path


def test_secure_config_round_trip_with_generated_key(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config.SecureConfig, "_get_keyring", lambda self: None)

    secure_config = config.SecureConfig()
    payload = {"paths": {"invoice_folder": "/invoices"}, "mode": "Test"}

    secure_config.save(payload)

    assert config.get_encrypted_config_path().exists()
    assert config.get_key_path().exists()

    reloaded = config.SecureConfig().load()
    assert reloaded == payload


def test_get_date_regex_matches_common_formats():
    patterns = config.get_date_regex()
    samples = ["2024-05-01", "5/1/2024", "Feb 3, 2024", "03 Mar 2024"]

    for sample in samples:
        assert any(p.search(sample) for p in patterns)


def test_get_file_regex_handles_invoice_and_default():
    invoice_regex = config.get_file_regex("invoice")
    match = invoice_regex.match("ACME invoice INV-001 SAFE MARINE.pdf")
    assert match

    customer, invoice_no, ship = match.groups()
    assert customer == "ACME"
    assert invoice_no == "INV-001"
    assert ship == "SAFE MARINE"

    default_regex = config.get_file_regex()
    assert default_regex.match("example.pdf")
    assert not default_regex.match("example.txt")
