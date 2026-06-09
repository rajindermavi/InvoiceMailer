"""Email construction and dispatch for Invoice Mailer.

MS Graph path: nicemail EmailClient handles OAuth token acquisition and sending.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import string
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_SUBJECT_TEMPLATE = "Invoices for ${head_office_name}"
DEFAULT_BODY_TEMPLATE = (
    "Dear ${head_office_name},\n\n"
    "Please find attached the invoices for your review.\n\n"
    "Best regards\n"
)

# Matches legacy {key} placeholders so stored configs using the old str.format
# syntax are transparently converted to ${key} for string.Template.
_BRACE_VAR = re.compile(r'\{(\w+)\}')


@dataclass
class ClientBatch:
    zip_path: Path
    email_list: List[str]
    head_office_name: str


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_recipients(email_list: list[str]) -> list[str]:
    """Split semicolon-separated entries, strip whitespace, drop empties and invalid addresses."""
    recipients: list[str] = []
    seen: set[str] = set()
    for entry in email_list:
        if not entry:
            continue
        for addr in entry.split(";"):
            addr = addr.strip()
            if not addr:
                continue
            if not _EMAIL_RE.match(addr):
                logger.warning("Skipping invalid email address: %r", addr)
                continue
            # Preserve order but avoid duplicates
            if addr in seen:
                continue
            seen.add(addr)
            recipients.append(addr)
    return recipients


def _render_templates(
    batch: ClientBatch,
    subject_template: str,
    body_template: str,
    sender_name: str,
    period: str,
) -> tuple[str, str]:
    try:
        year, month = str(period).split("-", 1)
    except Exception:
        logger.warning("Period %r is not in YYYY-MM format; {month}/{year} will be blank in templates", period)
        month, year = "", ""

    if isinstance(body_template, str):
        body_template = body_template.replace("\\n", "\n")
    if isinstance(subject_template, str):
        subject_template = subject_template.replace("\\n", "\n")

    fmt = {
        "head_office_name": batch.head_office_name,
        "contact_name": batch.head_office_name,
        "sender_name": sender_name,
        "month_year": period,
        "period": period,
        "month": month,
        "year": year,
    }

    def _render(template: str) -> str:
        # Convert legacy {key} → ${key} so stored configs keep working.
        normalised = _BRACE_VAR.sub(r'${\1}', template)
        return string.Template(normalised).safe_substitute(fmt)

    return _render(subject_template), _render(body_template)


# --------------------------------------------------------------------------- #
# Public send entry point                                                      #
# --------------------------------------------------------------------------- #

def send_all_emails(
    batches: List[ClientBatch],
    ms_email_address: str = "",
    ms_authority: str = "organizations",
    ms_client_id: str = "",
    dry_run: bool = False,
    subject_template: str = DEFAULT_SUBJECT_TEMPLATE,
    body_template: str = DEFAULT_BODY_TEMPLATE,
    sender_name: str = "Your Company",
    period: str = "last month",
    reporter_emails: Optional[List[str]] = None,
    show_message: Optional[Callable[[Any], None]] = None,
    passphrase: Optional[str] = None,
) -> str:
    """Send all batches via MS Graph and return an activity log string.

    Args:
        batches:            One ClientBatch per head-office aggregate group.
        ms_email_address:   Sender address for MS Graph.
        ms_authority:       MSAL authority – ``"organizations"`` or ``"consumers"``.
        dry_run:            When True, build emails but make no network calls.
        subject_template:   Format string; see module-level DEFAULT_SUBJECT_TEMPLATE.
        body_template:      Format string; see module-level DEFAULT_BODY_TEMPLATE.
        sender_name:        Populates ``{sender_name}`` in templates.
        period:             Billing period string, e.g. ``"2024-05"``.
        reporter_emails:    Recipients for the post-run summary email.
        show_message:       Callback passed to nicemail for device-code flow display.
        passphrase:         nicemail passphrase for its internal credential store.
    """
    reporter_emails = reporter_emails or []

    def _build_log(entries: list[str], is_dry_run: bool) -> str:
        sep = "\n" + ("-" * 40) + "\n"
        log = f"Email sending activity for period: {period}\n\n" + sep.join(entries) + sep
        if is_dry_run:
            log = f"<<<TEST ONLY DRY RUN>>>\n{log}\n<<<END TEST ONLY DRY RUN>>>"
        return log

    activity: list[str] = []

    if dry_run:
        for batch in batches:
            subject, body = _render_templates(batch, subject_template, body_template, sender_name, period)
            activity.append(
                f"Would send to {', '.join(batch.email_list)} with attachment {batch.zip_path}\n"
                f"Subject: {subject}\nBody:\n{body}"
            )
        return _build_log(activity, is_dry_run=True)

    if not ms_email_address:
        raise ValueError("MS email address is required.")
    _send_via_graph(
        batches,
        ms_email_address=ms_email_address,
        ms_authority=ms_authority,
        ms_client_id=ms_client_id,
        subject_template=subject_template,
        body_template=body_template,
        sender_name=sender_name,
        period=period,
        reporter_emails=reporter_emails,
        show_message=show_message,
        passphrase=passphrase,
        activity=activity,
    )

    return _build_log(activity, is_dry_run=False)


# --------------------------------------------------------------------------- #
# Transport implementations                                                    #
# --------------------------------------------------------------------------- #

_FERNET_MARKER = b"NICEMAIL_FERNET_V1\n"
_KDF_SALT = b"NICEMAIL_SECURECONFIG_V1"


class _PassphraseSecureConfig:
    """
    Drop-in replacement for nicemail's SecureConfig that uses passphrase-based
    Fernet only — no DPAPI, no keyring. Injected into EmailClient.secure_config
    to avoid the Windows DPAPI decryption failure when the key context changes.

    Uses the same key derivation and file path as nicemail so token caches
    written here are readable by a fixed nicemail build, and vice versa.
    """

    def __init__(self, passphrase: str | bytes) -> None:
        from cryptography.fernet import Fernet
        from platformdirs import user_config_dir

        if isinstance(passphrase, str):
            passphrase = passphrase.encode("utf-8")
        raw_key = hashlib.pbkdf2_hmac("sha256", passphrase, _KDF_SALT, 390_000, dklen=32)
        self._fernet = Fernet(base64.urlsafe_b64encode(raw_key))
        self._path = Path(user_config_dir("nicemail", appauthor=False)) / "config.enc"

    def load(self) -> dict:
        if not self._path.exists():
            return {}
        raw = self._path.read_bytes()
        payload = raw[len(_FERNET_MARKER):] if raw.startswith(_FERNET_MARKER) else raw
        try:
            return json.loads(self._fernet.decrypt(payload).decode("utf-8"))
        except Exception:
            # File was encrypted with a different key or method (e.g. DPAPI).
            # Return empty so the auth flow runs fresh rather than crashing.
            logger.warning(
                "Could not decrypt nicemail config at %s; starting fresh auth.", self._path
            )
            return {}

    def save(self, config_dict: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = self._fernet.encrypt(json.dumps(config_dict, indent=2).encode("utf-8"))
        self._path.write_bytes(_FERNET_MARKER + encrypted)


def _normalize_ms_authority(ms_authority: str) -> str:
    authority = (ms_authority or "").strip().lower()
    if authority in {"organizations", "organization"}:
        return "organization"
    if authority in {"consumers", "consumer"}:
        return "consumer"
    raise ValueError(
        "MS authority must be 'organizations'/'organization' or 'consumers'/'consumer'"
    )


def _send_via_graph(
    batches: List[ClientBatch],
    *,
    ms_email_address: str,
    ms_authority: str,
    ms_client_id: str,
    subject_template: str,
    body_template: str,
    sender_name: str,
    period: str,
    reporter_emails: list[str],
    show_message: Optional[Callable[[Any], None]],
    passphrase: Optional[str],
    activity: list[str],
) -> None:
    from nicemail import EmailClient

    client = EmailClient(
        backend="ms_graph",
        msal_config={
            "email_address": ms_email_address,
            "client_id": ms_client_id,
            "authority": _normalize_ms_authority(ms_authority),
        },
        passphrase=passphrase,
    )
    if passphrase is not None:
        client.secure_config = _PassphraseSecureConfig(passphrase)

    for batch in batches:
        subject, body = _render_templates(batch, subject_template, body_template, sender_name, period)
        recipients = sorted(set(normalize_recipients(batch.email_list)))
        kwargs: dict[str, Any] = {
            "to": recipients,
            "subject": subject,
            "body_html": f"<pre>{body}</pre>",
            "from_address": ms_email_address,
            "attachments": [str(batch.zip_path)],
        }
        if show_message is not None:
            kwargs["show_message"] = show_message
        try:
            client.send(**kwargs)
            activity.append(
                f"Sent via MS Auth to {', '.join(batch.email_list)} with attachment {batch.zip_path}\n"
                f"Subject: {subject}\nBody:\n{body}"
            )
        except Exception as exc:
            logger.error("Failed to send to %s: %s", batch.email_list, exc)
            activity.append(
                f"FAILED to send to {', '.join(batch.email_list)} with attachment {batch.zip_path}\n"
                f"Error: {exc}"
            )

    if reporter_emails and activity:
        log_text = "\n".join(activity)
        report_kwargs: dict[str, Any] = {
            "to": reporter_emails,
            "subject": f"Invoice mailer report for {period}",
            "body_html": f"<pre>{log_text}</pre>",
            "from_address": ms_email_address,
        }
        if show_message is not None:
            report_kwargs["show_message"] = show_message
        try:
            client.send(**report_kwargs)
        except Exception as exc:
            logger.error("Failed to send reporter summary email: %s", exc)


