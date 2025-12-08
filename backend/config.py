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
KEYRING_SERVICE = APP_NAME
KEYRING_USERNAME = "config_key"


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
pdf_rect_settings: Dict[str, Dict[str, float]] = {
    'inv_date': {
        'x0_pct': 0.01,
        'y0_pct': 0.3275,
        'x1_pct': 0.12,
        'y1_pct': 0.34,
    },
    'soa_date': {   
        'x0_pct': 0.72,
        'y0_pct': 0.0775,
        'x1_pct': 0.815,
        'y1_pct': 0.092,
    },
    'soa_office': {
        'x0_pct': 0.85,
        'y0_pct': 0.0775,
        'x1_pct': 0.92,
        'y1_pct': 0.092,
    }
}
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
        self._log(f"Storage directory: {get_storage_dir()}")
        self._log(f"Config path: {get_encrypted_config_path()}")
        self._log(f"DPAPI enabled: {self._use_dpapi}")

    def _log(self, message: str) -> None:
        print(f"[SecureConfig] {message}")

    def _init_dpapi(self) -> bool:
        """
        Try to enable DPAPI when on Windows. Falls back if unavailable.
        """
        if os.name != "nt":
            return False
        try:
            import win32crypt  # type: ignore
        except Exception:
            return False

        self._win32crypt = win32crypt
        return True

    def _get_keyring(self):
        try:
            import keyring  # type: ignore
        except Exception:
            self._log("Keyring module not available; will skip keyring.")
            return None
        return keyring

    def _load_key_from_keyring(self) -> bytes | None:
        keyring = self._get_keyring()
        if not keyring:
            return None
        try:
            stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except Exception:
            self._log("Keyring lookup failed; continuing without keyring.")
            return None
        if not stored:
            self._log("No key found in keyring.")
            return None
        try:
            self._log("Loaded key from keyring.")
            return stored.encode("utf-8")
        except Exception:
            self._log("Key from keyring could not be decoded; ignoring.")
            return None

    def _save_key_to_keyring(self, key: bytes) -> bool:
        keyring = self._get_keyring()
        if not keyring:
            return False
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, key.decode("utf-8"))
            self._log("Saved key to keyring.")
            return True
        except Exception:
            self._log("Failed to save key to keyring.")
            return False

    def _ensure_fernet(self) -> Fernet:
        if self._fernet is None:
            key = self._load_or_generate_key()
            self._fernet = Fernet(key)
        return self._fernet

    def _load_or_generate_key(self) -> bytes:
        # Prefer OS keyring so secrets are not written to disk.
        keyring_key = self._load_key_from_keyring()
        if keyring_key:
            return keyring_key

        key_file = get_key_path()
        if key_file.exists():
            self._log(f"Loading key from file: {key_file}")
            stored = key_file.read_bytes()
            if os.name == "nt":
                decrypted = self._dpapi_decrypt(stored)
                if decrypted:
                    self._log("Key file decrypted via DPAPI.")
                    stored = decrypted
            return stored

        key = Fernet.generate_key()
        self._log("Generated new Fernet key.")
        if self._save_key_to_keyring(key):
            return key

        # Fallback to a file; on Windows try to DPAPI-protect the key bytes.
        if os.name == "nt":
            encrypted = self._dpapi_encrypt(key)
            if encrypted is not None:
                self._log(f"Writing DPAPI-protected key file: {key_file}")
                key_file.write_bytes(encrypted)
                return key
            raise RuntimeError("Unable to protect encryption key on Windows (DPAPI/keyring unavailable).")

        self._log(f"Writing key file: {key_file}")
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
            encrypted = self._win32crypt.CryptProtectData(data, None, None, None, None, 0)[1]
        except Exception:
            self._use_dpapi = False
            return None

        if isinstance(encrypted, memoryview):
            return encrypted.tobytes()
        if isinstance(encrypted, (bytes, bytearray)):
            return bytes(encrypted)

        # Unexpected type; disable DPAPI so we fall back to Fernet.
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
                self._log(f"Loaded config via DPAPI from: {cfg_file}")
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

        self._log(f"Loaded config via Fernet from: {cfg_file}")
        return json.loads(decrypted.decode("utf-8"))

    def save(self, config_dict: dict) -> None:
        """Encrypt and save the config as JSON."""
        json_bytes = json.dumps(config_dict, indent=2).encode("utf-8")
        cfg_file = get_encrypted_config_path()

        if self._use_dpapi:
            encrypted = self._dpapi_encrypt(json_bytes)
            if encrypted is not None:
                self._log(f"Saving config with DPAPI to: {cfg_file}")
                cfg_file.write_bytes(encrypted)
                return

        fernet = self._ensure_fernet()
        encrypted = fernet.encrypt(json_bytes)
        self._log(f"Saving config with Fernet to: {cfg_file}")
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
