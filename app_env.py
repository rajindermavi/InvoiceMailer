"""
Common environment helpers shared between config handling and DB path logic.
"""

from __future__ import annotations

import os
import sys

APP_NAME = "InvoiceMailer"
DB_FILENAME = "invoice_mailer.sqlite3"


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
