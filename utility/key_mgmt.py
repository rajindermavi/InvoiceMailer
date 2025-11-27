
"""
Simple keyring helpers for storing and retrieving secrets (e.g., SMTP password).

Usage:
    pwd = get_or_prompt_secret("smtp_password", username="invoicemailer")
    delete_secret("smtp_password", username="invoicemailer")
"""

from __future__ import annotations

import getpass
from typing import Optional

from app_env import APP_NAME

try:
    import keyring
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise RuntimeError("keyring is required. Install with `pip install keyring`.") from exc


def _service_name(name: str | None = None) -> str:
    """Namespace secrets under the app name to avoid collisions."""
    base = APP_NAME
    if name:
        return f"{base}:{name}"
    return base


def get_or_prompt_secret(
    name: str,
    username: str = "invoicemailer",
    prompt: Optional[str] = None,
) -> str:
    """
    Look up a secret in the OS keyring; if missing, prompt the user and save it.

    Returns the secret value (never None). Raises ValueError if an empty string
    is entered at the prompt.
    """
    service = _service_name(name)
    existing = keyring.get_password(service, username)
    if existing:
        return existing

    if prompt is None:
        prompt = f"Enter {name.replace('_', ' ')} for {username}: "

    secret = getpass.getpass(prompt)
    if not secret:
        raise ValueError("No secret provided; aborting.")

    keyring.set_password(service, username, secret)
    return secret


def delete_secret(
    name: str,
    username: str = "invoicemailer",
) -> None:
    """Remove a stored secret from the OS keyring (no error if absent)."""
    service = _service_name(name)
    try:
        keyring.delete_password(service, username)
    except keyring.errors.PasswordDeleteError:
        # Nothing to delete; ignore.
        return
