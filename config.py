# config.py
from __future__ import annotations

import os
import sys
from pathlib import Path
import configparser
import re
import json
from typing import Dict

from app_env import APP_NAME, is_frozen_exe, get_app_env

DEFAULT_DATE_PATTERNS = [
    r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
    r"\b\d{1,2}[-/]\d{1,2}[-/](?:\d{2}|\d{4})\b",
]
DEFAULT_CONFIG_CONTENT = """\
# ===============================
# InvoiceMailer Configuration
# ===============================
# This file is created automatically on first run.
# Edit the folder paths below to match your environment.
#
# Use full Windows paths (e.g. C:\\Invoices\\Incoming).
# Avoid trailing slashes.
#
# After saving, restart the application.

[paths]
# Folder where new invoices appear
invoice_folder = D:\\Invoices

# Folder where SOA (statements of account) files live
soa_folder = D:\\SOA

# Folder where processed invoices should be archived
client_directory = C:\\client\\client_directory.xlsx

[email]
# Optional: override From: address
from_address =

# Optional: email subject prefix
subject_prefix = [Invoices]
"""

try:
    from dotenv import load_dotenv  # pip install python-dotenv
except ImportError:
    load_dotenv = None

def project_root() -> Path:
    # Where the script lives (or the temp dir PyInstaller uses)
    if is_frozen_exe():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent

def load_env_if_present() -> None:
    """Optional: only used in dev for .env overrides."""
    if load_dotenv is None:
        return
    env_path = project_root() / ".env"
    if env_path.exists():
        load_dotenv(env_path)

def get_config_path() -> Path:
    """
    Pick config.dev.ini in dev, config.ini in prod.

    - Dev:   project_root()/config.dev.ini
    - Prod:  %LOCALAPPDATA%\\InvoiceMailer\\config.ini
    """
    env = get_app_env()

    if env == "development":
        # simple: just use a dev config next to your code
        return project_root() / "config.dev.ini"

    # production
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        base = Path(local_appdata) / APP_NAME
    else:
        base = Path.home() / f".{APP_NAME.lower()}"
    base.mkdir(parents=True, exist_ok=True)
    return base / "config.ini"

def ensure_prod_config_exists(cfg_path: Path) -> None:
    """
    If in production and config.ini doesn't exist, create it with defaults.
    """
    if cfg_path.exists():
        return

    # Create default config.ini
    cfg_path.write_text(DEFAULT_CONFIG_CONTENT, encoding="utf-8")

def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg_path = get_config_path()
    if cfg_path.exists():
        cfg.read(cfg_path, encoding="utf-8")
    return cfg

# ---- Folder helpers ----

def _ensure_folder(path_str: str, fallback: Path) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_dir():
        # try to create
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            p = fallback
            p.mkdir(parents=True, exist_ok=True)
    return p

def _ensure_file(path_str: str, fallback: Path) -> Path:
    """
    Ensure a file path exists; if creation fails, use the fallback file.
    """
    p = Path(path_str).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and not p.is_file():
            raise IsADirectoryError(f"{p} is not a file")
        if not p.exists():
            p.touch()
        return p
    except Exception:
        fb = fallback.expanduser()
        fb.parent.mkdir(parents=True, exist_ok=True)
        if fb.exists() and not fb.is_file():
            raise IsADirectoryError(f"{fb} is not a file")
        if not fb.exists():
            fb.touch()
        return fb

def get_invoice_folder(cfg: configparser.ConfigParser) -> Path:
    default = project_root() / "invoices"
    path_str = cfg.get("paths", "invoice_folder", fallback=str(default))
    return _ensure_folder(path_str, fallback=default)

def get_soa_folder(cfg: configparser.ConfigParser) -> Path:
    default = project_root() / "soa"
    path_str = cfg.get("paths", "soa_folder", fallback=str(default))
    return _ensure_folder(path_str, fallback=default)

def get_client_directory(cfg: configparser.ConfigParser) -> Path:
    default = project_root() / "client_directory.xlsx"
    path_str = cfg.get("paths", "client_directory", fallback=str(default))
    return _ensure_file(path_str, fallback=default)

# ---- regex patterns ----

def _parse_pattern_list(raw_value: str) -> list[str]:
    raw = raw_value.strip()
    if not raw:
        return []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None

    # JSON array (preferred)
    if isinstance(parsed, list):
        patterns: list[str] = []
        for item in parsed:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                patterns.append(text)
        return patterns

    # Fallback: multiline INI value, one pattern per line (trailing commas allowed)
    multiline: list[str] = []
    for line in raw.splitlines():
        cleaned = line.strip().rstrip(",")
        if cleaned:
            multiline.append(cleaned)
    if multiline:
        return multiline

    # Last resort: treat the whole value as a single pattern
    return [raw]

def get_date_pattern(
    cfg: configparser.ConfigParser | None = None,
) -> list[re.Pattern[str]]:
    """
    Return compiled regex patterns for invoice dates.

    The list comes from [regex] invoice_date_patterns in the config file.
    If that section/option is missing or invalid, defaults are returned.
    """
    if cfg is None:
        cfg = load_config()

    raw_value = ""
    if cfg.has_section("regex"):
        raw_value = cfg.get("regex", "date_patterns", fallback="").strip()

    pattern_strings = _parse_pattern_list(raw_value) or DEFAULT_DATE_PATTERNS

    compiled: list[re.Pattern[str]] = []
    for pattern in pattern_strings:
        try:
            compiled.append(re.compile(pattern))
        except re.error:
            # Skip invalid entries
            continue

    if not compiled:
        compiled = [re.compile(p) for p in DEFAULT_DATE_PATTERNS]

    return compiled

def get_file_regex(
    cfg: configparser.ConfigParser | None = None,
    type: str | None = None
) -> re.Pattern[str]:
    default = '^([^\s]+).pdf'
    if cfg.has_section("regex"):
        pattern_str = cfg.get("regex", f"{type}_file_pattern", fallback=str(default))
    else:
        pattern_str = default
    
    return re.compile(pattern_str, re.IGNORECASE)

# ---- packaging and email ----

def get_packaging(cfg: configparser.ConfigParser | None = None) -> Dict[str,str]:
    default = 'head_office'
    if cfg.has_section("packaging"):
        agg = cfg.get("packaging", f"aggregate_by", fallback=str(default))
    else:
        agg = default
    return {'agg':agg}
