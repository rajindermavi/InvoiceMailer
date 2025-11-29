"""
db_path.py

Central place to decide where the SQLite DB file lives.

Features:
- Detects dev vs production mode.
- Uses LOCALAPPDATA on Windows in production.
- Falls back to a hidden folder in the home directory on non-Windows.
- Allows overriding the DB path via environment variable APP_DB_PATH.
- When run directly (python db_path.py), prints the chosen path and mode.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import APP_NAME, DB_FILENAME, get_app_env, is_frozen_exe

# Environment variables used:
#   APP_ENV     = "production" or "development" (optional)
#   APP_DB_PATH = full path to the DB file (optional; highest priority)


# ---------------------------------------------------------------------------
# Path builders
# ---------------------------------------------------------------------------

def get_explicit_db_path() -> Path | None:
    """
    If APP_DB_PATH is set, return that as a Path; otherwise None.

    This is the highest-priority override, useful for testing.
    """
    explicit = os.getenv("APP_DB_PATH")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return None


def get_dev_db_path() -> Path:
    """
    Development DB path:

        <directory_of_this_file>/data/invoice_mailer.sqlite3
    """
    base_dir = Path(__file__).resolve().parent
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / DB_FILENAME


def get_prod_db_path_windows() -> Path:
    """
    Production DB path on Windows:

        %LOCALAPPDATA%\\APP_NAME\\invoice_mailer.sqlite3
    """
    local_appdata = os.getenv("LOCALAPPDATA")
    if not local_appdata:
        # Very unusual, but fall back to home-based path
        return get_prod_db_path_posix_fallback()

    base = Path(local_appdata) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base / DB_FILENAME


def get_prod_db_path_posix_fallback() -> Path:
    """
    Production DB path on non-Windows (or if LOCALAPPDATA missing):

        ~/.app_name_lowercase/invoice_mailer.sqlite3
    """
    home = Path.home()
    base = home / f".{APP_NAME.lower()}"
    base.mkdir(parents=True, exist_ok=True)
    return base / DB_FILENAME


def get_prod_db_path() -> Path:
    """
    Production DB path, choosing the right platform-specific location.
    """
    if os.name == "nt":
        return get_prod_db_path_windows()
    else:
        return get_prod_db_path_posix_fallback()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_db_path() -> Path:
    """
    Main entry point: returns the full path to the DB file.

    Priority:
      1. APP_DB_PATH (explicit override)
      2. Production path if env is "production"
      3. Development path otherwise
    """
    explicit = get_explicit_db_path()
    if explicit is not None:
        return explicit

    env = get_app_env()
    if env == "production":
        return get_prod_db_path()
    else:
        return get_dev_db_path()


def describe_db_path() -> str:
    """
    Return a human-readable description of the DB configuration.
    """
    env = get_app_env()
    explicit = os.getenv("APP_DB_PATH")
    frozen = is_frozen_exe()
    path = get_db_path()

    lines = [
        f"APP_ENV      : {env!r}",
        f"Frozen exe   : {frozen}",
        f"APP_DB_PATH  : {explicit!r}",
        f"OS name      : {os.name!r}",
        f"Resolved path: {str(path)}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Debug / manual test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Run `python db_path.py` to see where your DB will go.
    print(describe_db_path())
