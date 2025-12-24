from __future__ import annotations

import base64
from typing import Optional, Callable

import msal
import smtplib
from email.message import EmailMessage
try:
    from tkinter import messagebox  # GUI popup for device-code instructions
except Exception:  # pragma: no cover - fallback for non-GUI contexts
    messagebox = None

from backend.config import SecureConfig

CLIENT_ID = '35f3b77e-a368-409d-bec4-5ce2e246f1f9'
TENANT_ID = 'a604e3a8-7a82-4088-8fd0-52ec4f0ccfd9'
MS_SCOPES = ["https://outlook.office365.com/SMTP.Send"]
DEFAULT_MS_EX_DELEGATED = "https://outlook.office365.com/.default"

# ---------------------------------------------------------------------------
# Token provider using MSAL device code flow
# ---------------------------------------------------------------------------
    
class MSalDeviceCodeTokenProvider:
    """
    Handles access token acquisition for a single mailbox using MSAL Device Code Flow.
    """

    TOKEN_CACHE_KEY = "ms_token_cache"
    MS_USERNAME_KEY = "ms_username"

    def __init__(self, secure_config: SecureConfig | None = None, show_message: Callable[[object], None] | None = None) -> None:
        self.secure_config = secure_config
        self._show_message = show_message

        self._cache = msal.SerializableTokenCache()
        self._load_cache()

        authority = f"https://login.microsoftonline.com/{TENANT_ID}"

        self._app = msal.PublicClientApplication(
            client_id=CLIENT_ID,
            authority=authority,
            token_cache=self._cache,
        )

    def _load_cache(self) -> None:
        if self.secure_config:
            data = self.secure_config.load() or {}
            self.ms_username = data.get(self.MS_USERNAME_KEY)
            serialized_cache = data.get(self.TOKEN_CACHE_KEY)
            if serialized_cache:
                try:
                    self._cache.deserialize(serialized_cache)
                    return
                except Exception:
                    self._cache = msal.SerializableTokenCache()

    def _save_cache_if_changed(self) -> None:
        if self._cache.has_state_changed:
            serialized = self._cache.serialize()
            if self.secure_config:
                data = self.secure_config.load() or {}
                data[self.TOKEN_CACHE_KEY] = serialized
                # Also set a lightweight flag for UI display.
                if getattr(self, "ms_username", None):
                    data[self.MS_USERNAME_KEY] = self.ms_username
                self.secure_config.save(data)

    def acquire_token(self, interactive: bool = True) -> str:
        """
        Get a valid access token for cfg.scopes.

        1. Try silent acquisition from cache.
        2. If not available and interactive=True, run device code flow.
        3. Save cache if changed.
        Raises RuntimeError if token cannot be obtained.
        """
        scopes = MS_SCOPES
        # Try silent first, using account matching the email (if any)
        accounts = self._app.get_accounts(username=self.ms_username)
        account = accounts[0] if accounts else None

        result = self._app.acquire_token_silent(scopes, account=account)

        if not result and interactive:
            # Initiate device code flow
            flow = self._app.initiate_device_flow(scopes=scopes)
            if "user_code" not in flow:
                raise RuntimeError(f"Failed to initiate device code flow: {flow!r}")

            self._display_message(flow)

            # This call blocks until user completes auth or it times out.
            result = self._app.acquire_token_by_device_flow(flow)

        if not result or "access_token" not in result:
            err = None
            if isinstance(result, dict):
                err = result.get("error_description") or result.get("error")
            raise RuntimeError(f"Could not obtain access token. Details: {err!r}")

        # Capture username from the auth result so we can persist it with the cache.
        username = self._extract_username(result)
        if username:
            self.ms_username = username

        self._save_cache_if_changed()
        return result["access_token"]

    def _display_message(self, msg: object) -> None:
        """
        Show device-flow instructions.
        `msg` can be the flow dict or a plain string; callbacks get the raw object.
        """
        if callable(self._show_message):
            self._show_message(msg)
            return
        text = msg.get("message") if isinstance(msg, dict) else str(msg)
        if messagebox:
            messagebox.showinfo("Microsoft Sign-in", text)
            return
        print(text, flush=True)

    def _extract_username(self, result: dict) -> str | None:
        """
        Pull a username/email from an MSAL token result, if present.
        """
        if not isinstance(result, dict):
            return None
        claims = result.get("id_token_claims") or {}
        return (
            claims.get("preferred_username")
            or claims.get("upn")
            or result.get("username")
        )
    
 
# ---------------------------------------------------------------------------
# SMTP helpers (XOAUTH2 + EmailMessage sending)
# ---------------------------------------------------------------------------

def _build_xoauth2_string(email_address: str, access_token: str) -> str:
    """
    Build the XOAUTH2 auth string for SMTP AUTH.
    """
    # Note: \1 is the control character ^A
    return f"user={email_address}\1auth=Bearer {access_token}\1\1"


def connect_smtp_with_oauth(
    token_provider: Optional[MSalDeviceCodeTokenProvider] = None,
    interactive: bool = True,
    secure_config: SecureConfig | None = None,
) -> smtplib.SMTP:
    """
    Create and return an authenticated smtplib.SMTP instance using XOAUTH2.

    - Acquires an access token (silent + optional device-code interactive).
    - Connects to SMTP host and performs AUTH XOAUTH2.
    - Raises smtplib.SMTPAuthenticationError if AUTH fails.

    The caller is responsible for closing the SMTP connection, e.g.:

        with connect_smtp_with_oauth(cfg, token_provider) as smtp:
            smtp.send_message(msg)
    """
    if token_provider is None:
        token_provider = MSalDeviceCodeTokenProvider(secure_config=secure_config)

    access_token = token_provider.acquire_token(interactive=interactive)

    smtp = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=60)
    smtp.ehlo()
    if cfg.use_starttls:
        smtp.starttls()
        smtp.ehlo()

    auth_str = _build_xoauth2_string(cfg.email_address, access_token)
    auth_b64 = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")

    code, resp = smtp.docmd("AUTH", "XOAUTH2 " + auth_b64)
    if code != 235:
        # AUTH failed; close connection and raise
        smtp.quit()
        raise smtplib.SMTPAuthenticationError(code, resp)

    return smtp


def send_email_via_smtp_oauth(
    cfg: SMTPDeviceCodeConfig,
    msg: EmailMessage,
    token_provider: Optional[DeviceCodeTokenProvider] = None,
    interactive: bool = True,
    secure_config: SecureConfig | None = None,
) -> None:
    """
    Convenience wrapper:
    - Connects via OAuth2
    - Sends a single EmailMessage
    - Closes the connection

    `msg["From"]` will be set to cfg.email_address if not already set.
    """
    if not msg.get("From"):
        msg["From"] = cfg.email_address

    with connect_smtp_with_oauth(
        cfg,
        token_provider,
        interactive=interactive,
        secure_config=secure_config,
    ) as smtp:
        smtp.send_message(msg)
