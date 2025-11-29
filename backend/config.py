# config.py
from __future__ import annotations

import os
import sys
from pathlib import Path
import configparser
import re
import json
from typing import Dict, Any

from cryptography.fernet import Fernet

APP_NAME = "InvoiceMailer"
DB_FILENAME = "invoice_mailer.sqlite3"

DEFAULT_DATE_PATTERNS = [
    r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
    r"\b\d{1,2}[-/]\d{1,2}[-/](?:\d{2}|\d{4})\b",
]

###### Common environment helpers ######

def is_frozen_exe() -> bool:
    """Detects whether we are running as a bundled executable."""
    return getattr(sys, "frozen", False)

def get_app_env() -> str:
    """
    Returns 'development' or 'production' based on APP_ENV or executable state.
    """
    env = os.getenv("APP_ENV", "").strip().lower()
    if env in {"prod", "production"}:
        return "production"
    if env in {"dev", "development"}:
        return "development"

    if is_frozen_exe():
        return "production"
    return "development"

def get_storage_dir() -> Path:
    """Where encrypted config + key live."""
    env = get_app_env()
    if env == "development":
        return Path.cwd()

    # production
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        base = Path(local_appdata) / APP_NAME
    else:
        base = Path.home() / f".{APP_NAME.lower()}"

    base.mkdir(parents=True, exist_ok=True)
    return base

##### Encrypted Config Utility #####

def get_key_path() -> Path:
    return get_storage_dir() / "encryption.key"

def get_encrypted_config_path() -> Path:
    return get_storage_dir() / "config.enc"

class SecureConfig:
    def __init__(self):
        self._win32crypt: Any | None = None
        self._use_dpapi = self._init_dpapi()
        self._fernet: Fernet | None = None

    def _init_dpapi(self) -> bool:
        """
        Try to enable DPAPI when on Windows + production. Falls back if unavailable.
        """
        if os.name != "nt":
            return False
        if get_app_env() != "production":
            return False
        try:
            import win32crypt  # type: ignore
        except Exception:
            return False

        self._win32crypt = win32crypt
        return True

    def _ensure_fernet(self) -> Fernet:
        if self._fernet is None:
            key = self._load_or_generate_key()
            self._fernet = Fernet(key)
        return self._fernet

    def _load_or_generate_key(self) -> bytes:
        key_file = get_key_path()
        if key_file.exists():
            return key_file.read_bytes()

        key = Fernet.generate_key()
        key_file.write_bytes(key)
        return key

    def _dpapi_decrypt(self, data: bytes) -> bytes | None:
        if not self._win32crypt:
            return None
        try:
            return self._win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]
        except Exception:
            self._use_dpapi = False
            return None

    def _dpapi_encrypt(self, data: bytes) -> bytes | None:
        if not self._win32crypt:
            return None
        try:
            return self._win32crypt.CryptProtectData(data, None, None, None, None, 0)[1]
        except Exception:
            self._use_dpapi = False
            return None

    def load(self) -> dict:
        """Decrypt and load the config from config.enc."""
        cfg_file = get_encrypted_config_path()
        if not cfg_file.exists():
            return {}  # no config yet

        encrypted = cfg_file.read_bytes()

        if self._use_dpapi:
            decrypted = self._dpapi_decrypt(encrypted)
            if decrypted is not None:
                try:
                    return json.loads(decrypted.decode("utf-8"))
                except Exception:
                    return {}

        fernet = self._ensure_fernet()
        try:
            decrypted = fernet.decrypt(encrypted)
        except Exception:
            # If corrupt, return empty (or raise)
            return {}

        return json.loads(decrypted.decode("utf-8"))

    def save(self, config_dict: dict) -> None:
        """Encrypt and save the config as JSON."""
        json_bytes = json.dumps(config_dict, indent=2).encode("utf-8")
        cfg_file = get_encrypted_config_path()

        if self._use_dpapi:
            encrypted = self._dpapi_encrypt(json_bytes)
            if encrypted is not None:
                cfg_file.write_bytes(encrypted)
                return

        fernet = self._ensure_fernet()
        encrypted = fernet.encrypt(json_bytes)
        cfg_file.write_bytes(encrypted)



#####
# 
# def project_root() -> Path:
#     # Where the script lives (or the temp dir PyInstaller uses)
#     if is_frozen_exe():
#         return Path(sys._MEIPASS)  # type: ignore[attr-defined]
#     return Path(__file__).resolve().parent
# 
# def load_env_if_present() -> None:
#     """Optional: only used in dev for .env overrides."""
#     if load_dotenv is None:
#         return
#     env_path = project_root() / ".env"
#     if env_path.exists():
#         load_dotenv(env_path)
# 
# def get_config_path() -> Path:
#     """
#     Pick config.dev.ini in dev, config.ini in prod.
# 
#     - Dev:   project_root()/config.dev.ini
#     - Prod:  %LOCALAPPDATA%\\InvoiceMailer\\config.ini
#     """
#     env = get_app_env()
# 
#     if env == "development":
#         # simple: just use a dev config next to your code
#         return project_root() / "config.dev.ini"
# 
#     # production
#     local_appdata = os.getenv("LOCALAPPDATA")
#     if local_appdata:
#         base = Path(local_appdata) / APP_NAME
#     else:
#         base = Path.home() / f".{APP_NAME.lower()}"
#     base.mkdir(parents=True, exist_ok=True)
#     return base / "config.ini"
# 
# def load_config() -> configparser.ConfigParser:
#     cfg = configparser.ConfigParser()
#     cfg_path = get_config_path()
#     if cfg_path.exists():
#         cfg.read(cfg_path, encoding="utf-8")
#     return cfg

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
    default = get_storage_dir() / "invoices"
    path_str = cfg.get("paths", "invoice_folder", fallback=str(default))
    return _ensure_folder(path_str, fallback=default)

def get_soa_folder(cfg: configparser.ConfigParser) -> Path:
    default = get_storage_dir() / "soa"
    path_str = cfg.get("paths", "soa_folder", fallback=str(default))
    return _ensure_folder(path_str, fallback=default)

def get_client_directory(cfg: configparser.ConfigParser) -> Path:
    default = get_storage_dir() / "client_directory.xlsx"
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
