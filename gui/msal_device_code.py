from __future__ import annotations

import base64
from typing import Optional, Callable, Dict

import msal
import smtplib
from email.message import EmailMessage
from email.utils import getaddresses
try:
    from tkinter import messagebox  # GUI popup for device-code instructions
except Exception:  # pragma: no cover - fallback for non-GUI contexts
    messagebox = None

from backend.config import SecureConfig
import requests
import base64

CLIENT_ID_UNIV = '7a55d55b-0653-4ae7-9d2b-f63929063499'
GRAPH_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
MS_SCOPES = ["https://outlook.office365.com/SMTP.Send"]
#GRAPH_SCOPES = ["Mail.Send"]
GRAPH_MAIL_SCOPES = ["https://graph.microsoft.com/Mail.Send"]
#DEFAULT_MS_EX_DELEGATED = "https://outlook.office365.com/.default"

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

        
        authority = "https://login.microsoftonline.com/common"


        self._app = msal.PublicClientApplication(
            client_id=CLIENT_ID_UNIV,
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

    def acquire_token(self, interactive: bool = True, scopes: list[str] | None = None) -> str:
        """
        Get a valid access token for cfg.scopes.

        1. Try silent acquisition from cache.
        2. If not available and interactive=True, run device code flow.
        3. Save cache if changed.
        Raises RuntimeError if token cannot be obtained.
        """
        scopes = scopes or GRAPH_MAIL_SCOPES
        # Try silent first, using account matching the email (if any)
        accounts = self._app.get_accounts()
        account = accounts[0] if accounts else None
        #print(account)
        result = self._app.acquire_token_silent(scopes, account=account)
        #print(result)
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
    cfg: Dict,
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
    host = cfg.get("ms_smtp_host") or "smtp.office365.com"
    port = cfg.get("ms_smtp_port") or 587
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid MS SMTP port: {port!r}") from None

    if token_provider is None:
        token_provider = MSalDeviceCodeTokenProvider(secure_config=secure_config)

    user_email = cfg.get("ms_email_address") or getattr(token_provider, "ms_username", None)

    if not user_email:
        raise ValueError("MS email address is required to send mail via OAuth.")

    use_starttls = cfg.get("ms_use_starttls")
    if use_starttls is None:
        use_starttls = True

    access_token = token_provider.acquire_token(interactive=interactive)

    smtp = smtplib.SMTP(host, port, timeout=60)
    smtp.ehlo()
    if use_starttls:
        smtp.starttls()
        smtp.ehlo()

    auth_str = _build_xoauth2_string(user_email, access_token)
    
    auth_b64 = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")

    code, resp = smtp.docmd("AUTH", "XOAUTH2 " + auth_b64)
    if code != 235:
        # AUTH failed; close connection and raise
        smtp.quit()
        raise smtplib.SMTPAuthenticationError(code, resp)

    return smtp


def send_email_via_smtp_oauth(
    cfg: Dict,
    msg: EmailMessage,
    token_provider: Optional[MSalDeviceCodeTokenProvider] = None,
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
    if "ms_token" in cfg:
        cfg = cfg.get("ms_token") or {}
    if not cfg:
        raise ValueError("Missing ms_token configuration for MS OAuth SMTP send.")

    if not msg.get("From"):
        msg["From"] = cfg.get('ms_email_address')
    with connect_smtp_with_oauth(
        cfg,
        token_provider,
        interactive=interactive,
        secure_config=secure_config,
    ) as smtp:
        smtp.send_message(msg)


## --------------------------------------------------------------
## Graph email helpers
## --------------------------------------------------------------

class GraphMailClient:
    def __init__(self, access_token: str, from_address: str) -> None:
        self._access_token = access_token
        self._from_address = from_address

        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def send_message(self, msg: EmailMessage) -> None:
        payload = _emailmessage_to_graph_payload(
            msg,
            from_address=self._from_address,
        )

        resp = requests.post(
            GRAPH_SENDMAIL_URL,
            headers=self._headers,
            json=payload,
            timeout=30,
        )

        if resp.status_code not in (200, 202):
            raise RuntimeError(
                f"Graph sendMail failed: {resp.status_code} {resp.text}"
            )

    def __enter__(self) -> "GraphMailClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # nothing to close (HTTP)
        return None


def connect_graph_with_oauth(
    cfg: Dict,
    token_provider: Optional[MSalDeviceCodeTokenProvider] = None,
    interactive: bool = True,
    secure_config: SecureConfig | None = None,
) -> GraphMailClient:
    """
    Create and return a GraphMailClient using OAuth2.

    - Acquires an access token (silent + optional device-code interactive).
    - Prepares Graph sendMail client.
    - Raises RuntimeError if token or config is invalid.

    Usage:

        with connect_graph_with_oauth(cfg, token_provider) as graph:
            graph.send_message(msg)
    """
    if token_provider is None:
        token_provider = MSalDeviceCodeTokenProvider(
            secure_config=secure_config
        )

    from_address = cfg.get("ms_email_address") or getattr(
        token_provider, "ms_username", None
    )

    if not from_address:
        raise ValueError("MS email address is required to send mail via Graph.")

    access_token = token_provider.acquire_token(
        interactive=interactive,
        scopes=GRAPH_MAIL_SCOPES,
    )

    return GraphMailClient(
        access_token=access_token,
        from_address=from_address,
    )


def send_email_via_graph(
    cfg: Dict,
    msg: EmailMessage,
    token_provider: Optional[MSalDeviceCodeTokenProvider] = None,
    interactive: bool = True,
    secure_config: SecureConfig | None = None,
) -> None:
    """
    Convenience wrapper:
    - Connects via Microsoft Graph
    - Sends a single EmailMessage
    - Cleans up

    `msg["From"]` will be set to cfg["ms_email_address"] if not already set.
    """
    if "ms_token" in cfg:
        cfg = cfg.get("ms_token") or {}
    if not cfg:
        raise ValueError("Missing ms_token configuration for MS Graph send.")

    if not msg.get("From"):
        msg["From"] = cfg.get("ms_email_address")

    with connect_graph_with_oauth(
        cfg,
        token_provider,
        interactive=interactive,
        secure_config=secure_config,
    ) as graph:
        graph.send_message(msg)


def _emailmessage_to_graph_payload(
    msg: EmailMessage,
    from_address: str,
) -> Dict:
    def _body_content(msg: EmailMessage) -> tuple[str, str]:
        """
        Returns (content, graph_content_type) where graph_content_type is
        either "Text" or "HTML".
        """
        # Prefer a plain part, fall back to HTML, then to the raw content.
        preferred_part = msg.get_body(preferencelist=("plain", "html"))
        if preferred_part:
            content_type = preferred_part.get_content_type()
            content = preferred_part.get_content()
        elif not msg.is_multipart():
            content_type = msg.get_content_type()
            content = msg.get_content()
        else:
            # Multipart without a text part; send an empty text body.
            content_type = "text/plain"
            content = ""

        graph_type = "HTML" if content_type == "text/html" else "Text"
        return content or "", graph_type

    to_addrs = []
    for _, addr in getaddresses(msg.get_all("To") or []):
        if addr:
            to_addrs.append({"emailAddress": {"address": addr}})

    body_text, body_type = _body_content(msg)

    payload = {
        "message": {
            "subject": msg.get("Subject", ""),
            "body": {
                "contentType": body_type,
                "content": body_text,
            },
            "from": {
                "emailAddress": {"address": from_address}
            },
            "toRecipients": to_addrs,
        }
    }

    # Attachments (optional, but important for InvoiceMailer)
    attachments = []
    for part in msg.iter_attachments():
        filename = part.get_filename()
        content = part.get_payload(decode=True)
        if filename and content:
            attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": filename,
                "contentBytes": base64.b64encode(content).decode("utf-8"),
            })

    if attachments:
        payload["message"]["attachments"] = attachments

    return payload
