# config.py
from __future__ import annotations

import os
import sys
from pathlib import Path
import re
import json
from typing import Dict, Any

from cryptography.fernet import Fernet

APP_NAME = "InvoiceMailer"
DB_FILENAME = "invoice_mailer.sqlite3"


##### REGEX DEFAULTS #####

date_patterns = [
    r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
    r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{2,4}\b",
    r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\s+\d{2,4}\b"
]

file_patterns = {
    'invoice': r"^([^\s]+)\s+invoice\s+([^\s]+)\s+(.+)\.pdf$",
    'soa': r"^Statement of Account for- ([A-Za-z0-9]+)\s+(.+?)\s*\.PDF$"
}

##### PDF EXTRACTION SETTINGS #####

# Percent-based box (0–1), top-left (x0, y0) to bottom-right (x1, y1)
inv_date_x0_pct = 0.01
inv_date_y0_pct = 0.3275
inv_date_x1_pct = 0.12
inv_date_y1_pct = 0.34

soa_date_x0_pct = 0.72
soa_date_y0_pct = 0.0775
soa_date_x1_pct = 0.815
soa_date_y1_pct = 0.092

soa_office_x0_pct = 0.85
soa_office_y0_pct = 0.0775
soa_office_x1_pct = 0.92
soa_office_y1_pct = 0.092

#[processing]
# Which page index to read (0 = first page)
page_index = 0

# If true, fall back to OCR when text extraction fails
try_ocr_if_needed = True

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

# ---- regex patterns ----

def get_date_regex() -> list[re.Pattern[str]]:
    """
    Return compiled regex patterns for invoice dates.

    The list comes from [regex] invoice_date_patterns in the config file.
    If that section/option is missing or invalid, defaults are returned.
    """
    return [re.compile(p) for p in date_patterns]

def get_file_regex( type: str | None = None
) -> re.Pattern[str]:
    default = '^([^\s]+).pdf'
    pattern_str = file_patterns.get(type) or default
    return re.compile(pattern_str, re.IGNORECASE)

