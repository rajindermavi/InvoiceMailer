from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "InvoiceMailer"  # change to your app name


def is_frozen_exe() -> bool:
    """
    True if running as a bundled exe (PyInstaller, cx_Freeze, etc.).
    """
    return getattr(sys, "frozen", False)


def in_production_mode() -> bool:
    """
    Decide whether we're in 'production'.

    You can define this however you like. Here:
      - APP_ENV=production forces production
      - OR running as a frozen exe implies production
    """
    env = os.getenv("APP_ENV", "").lower()
    if env == "production":
        return True
    if is_frozen_exe():
        return True
    return False


def get_dev_db_path() -> Path:
    """
    DB path for development: <project_root>/data/invoice_mailer.sqlite3
    """
    base_dir = Path(__file__).resolve().parent
    data_dir = base_dir / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir / "invoice_mailer.sqlite3"


def get_prod_db_path() -> Path:
    """
    DB path for production on Windows:
      %LOCALAPPDATA%\\InvoiceMailer\\invoice_mailer.sqlite3

    Falls back to home directory if LOCALAPPDATA is missing.
    """
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        base = Path(local_appdata) / APP_NAME
    else:
        # very unlikely, but just in case
        base = Path.home() / f".{APP_NAME.lower()}"

    base.mkdir(parents=True, exist_ok=True)
    return base / "invoice_mailer.sqlite3"


def get_db_path() -> Path:
    """
    Public function: call this to get the correct DB path.
    """
    if in_production_mode():
        return get_prod_db_path()
    else:
        return get_dev_db_path()
