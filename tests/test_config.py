import configparser
from pathlib import Path

import pytest

import config


def _write_config(tmp_path: Path, invoice: Path, soa: Path, archive: Path) -> None:
    cfg_text = f"""
[paths]
invoice_folder = {invoice}
soa_folder = {soa}
archive_folder = {archive}

[email]
from_address = billing@example.com
subject_prefix = [Invoices]
"""
    (tmp_path / "config.dev.ini").write_text(cfg_text.strip(), encoding="utf-8")


def test_load_config_reads_dev_ini(tmp_path, monkeypatch):
    invoice_dir = tmp_path / "invoices_dir"
    soa_dir = tmp_path / "soa_dir"
    archive_dir = tmp_path / "archive_dir"
    _write_config(tmp_path, invoice_dir, soa_dir, archive_dir)

    monkeypatch.setattr(config, "project_root", lambda: tmp_path)
    monkeypatch.setattr(config, "get_app_env", lambda: "development")

    cfg = config.load_config()

    assert cfg.get("paths", "invoice_folder") == str(invoice_dir)
    assert cfg.get("paths", "soa_folder") == str(soa_dir)
    assert cfg.get("paths", "archive_folder") == str(archive_dir)
    assert cfg.get("email", "from_address") == "billing@example.com"


def test_folder_helpers_use_config_paths(tmp_path, monkeypatch):
    invoice_dir = tmp_path / "configured" / "invoices"
    soa_dir = tmp_path / "configured" / "soa"
    archive_dir = tmp_path / "configured" / "archive"
    _write_config(tmp_path, invoice_dir, soa_dir, archive_dir)

    monkeypatch.setattr(config, "project_root", lambda: tmp_path)
    monkeypatch.setattr(config, "get_app_env", lambda: "development")

    cfg = config.load_config()

    inv_path = config.get_invoice_folder(cfg)
    soa_path = config.get_soa_folder(cfg)
    archive_path = config.get_archive_folder(cfg)

    assert inv_path == invoice_dir
    assert soa_path == soa_dir
    assert archive_path == archive_dir

    assert invoice_dir.exists()
    assert soa_dir.exists()
    assert archive_dir.exists()


def test_folder_helpers_fallback_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "project_root", lambda: tmp_path)

    cfg = configparser.ConfigParser()

    inv_path = config.get_invoice_folder(cfg)
    soa_path = config.get_soa_folder(cfg)
    archive_path = config.get_archive_folder(cfg)

    assert inv_path == tmp_path / "invoices"
    assert soa_path == tmp_path / "soa"
    assert archive_path == tmp_path / "archive"
