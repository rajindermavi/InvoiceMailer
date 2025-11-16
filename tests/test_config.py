import configparser
import json
from pathlib import Path

import config


def _write_config(
    tmp_path: Path,
    invoice: Path,
    soa: Path,
    archive: Path,
    *,
    include_regex: bool = True,
    regex_patterns: list[str] | None = None,
) -> None:
    parser = configparser.ConfigParser()
    parser["paths"] = {
        "invoice_folder": str(invoice),
        "soa_folder": str(soa),
        "archive_folder": str(archive),
    }
    parser["email"] = {
        "from_address": "billing@example.com",
        "subject_prefix": "[Invoices]",
    }
    if include_regex:
        patterns = regex_patterns or [
            r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
            r"\b\d{1,2}[-/]\d{1,2}[-/](?:\d{2}|\d{4})\b",
        ]
        parser["regex"] = {
            "invoice_date_patterns": json.dumps(patterns, indent=4),
        }

    with (tmp_path / "config.dev.ini").open("w", encoding="utf-8") as fp:
        parser.write(fp)


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


def test_get_date_pattern_reads_regex_section(tmp_path, monkeypatch):
    invoice_dir = tmp_path / "invoices_dir"
    soa_dir = tmp_path / "soa_dir"
    archive_dir = tmp_path / "archive_dir"
    custom_patterns = [r"\bFOO\b", r"\d{2}/\d{2}/\d{4}"]
    _write_config(
        tmp_path,
        invoice_dir,
        soa_dir,
        archive_dir,
        regex_patterns=custom_patterns,
    )

    monkeypatch.setattr(config, "project_root", lambda: tmp_path)
    monkeypatch.setattr(config, "get_app_env", lambda: "development")

    cfg = config.load_config()
    patterns = config.get_date_pattern(cfg)

    assert [p.pattern for p in patterns] == custom_patterns


def test_get_date_pattern_defaults_when_missing_section(tmp_path, monkeypatch):
    invoice_dir = tmp_path / "invoices_dir"
    soa_dir = tmp_path / "soa_dir"
    archive_dir = tmp_path / "archive_dir"
    _write_config(
        tmp_path,
        invoice_dir,
        soa_dir,
        archive_dir,
        include_regex=False,
    )

    monkeypatch.setattr(config, "project_root", lambda: tmp_path)
    monkeypatch.setattr(config, "get_app_env", lambda: "development")

    cfg = config.load_config()
    patterns = config.get_date_pattern(cfg)

    assert [p.pattern for p in patterns] == config.DEFAULT_DATE_PATTERNS


def test_default_date_pattern_rejects_three_digit_years(tmp_path, monkeypatch):
    # Ensure default pattern doesn't accept 3-digit years like 200
    monkeypatch.setattr(config, "project_root", lambda: tmp_path)
    cfg = configparser.ConfigParser()
    compiled = config.get_date_pattern(cfg)

    short_year = "11/15/20"
    three_digit_year = "11/15/200"
    four_digit_year = "11/15/2000"

    # Match 2 or 4-digit years, but not 3-digit
    assert all(p.search(short_year) for p in compiled)
    assert not any(p.search(three_digit_year) for p in compiled)
    assert any(p.search(four_digit_year) for p in compiled)
