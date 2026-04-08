"""Email construction and dispatch for Invoice Mailer.

MS Graph path: nicemail EmailClient handles OAuth token acquisition and sending.
SMTP path:     smtplib with optional STARTTLS and login.
"""
from __future__ import annotations

import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any, List, Optional

DEFAULT_SUBJECT_TEMPLATE = "Invoices for {head_office_name}"
DEFAULT_BODY_TEMPLATE = (
    "Dear {head_office_name},\n\n"
    "Please find attached the invoices for your review.\n\n"
    "Best regards,\n"
    "Your Company"
)


@dataclass
class ClientBatch:
    zip_path: Path
    email_list: List[str]
    head_office_name: str


@dataclass
class SMTPConfig:
    host: str
    port: int
    username: str
    password: str
    from_addr: str
    use_tls: bool = True


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def normalize_recipients(email_list: list[str]) -> list[str]:
    """Split semicolon-separated entries, strip whitespace, drop empties."""
    recipients: list[str] = []
    for entry in email_list:
        if not entry:
            continue
        for addr in entry.split(";"):
            addr = addr.strip()
            if addr:
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
    return subject_template.format(**fmt), body_template.format(**fmt)


def build_email(
    batch: ClientBatch,
    from_addr: str,
    subject_template: str,
    body_template: str,
    sender_name: str,
    period: str,
) -> EmailMessage:
    """Build an EmailMessage with the ZIP attached. Used by the SMTP path."""
    subject, body = _render_templates(batch, subject_template, body_template, sender_name, period)

    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = ", ".join(sorted(set(normalize_recipients(batch.email_list))))
    msg["Subject"] = subject
    msg.set_content(body)

    with batch.zip_path.open("rb") as f:
        file_data = f.read()
    msg.add_attachment(
        file_data,
        maintype="application",
        subtype="zip",
        filename=batch.zip_path.name,
    )
    return msg


# --------------------------------------------------------------------------- #
# Public send entry point                                                      #
# --------------------------------------------------------------------------- #

def send_all_emails(
    batches: List[ClientBatch],
    email_auth_method: str,
    smtp_conf: SMTPConfig,
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
    """Send all batches and return an activity log string.

    Args:
        batches:            One ClientBatch per head-office aggregate group.
        email_auth_method:  ``"smtp"`` or ``"ms_auth"``.
        smtp_conf:          SMTP connection parameters (used when auth=smtp).
        ms_email_address:   Sender address for MS Graph (used when auth=ms_auth).
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
    use_ms_auth = (email_auth_method or "smtp").lower() == "ms_auth"

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

    if use_ms_auth:
        if not ms_email_address:
            raise ValueError("MS Auth email address is required when email_auth_method is 'ms_auth'.")
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
    else:
        _send_via_smtp(
            batches,
            smtp_conf=smtp_conf,
            subject_template=subject_template,
            body_template=body_template,
            sender_name=sender_name,
            period=period,
            reporter_emails=reporter_emails,
            activity=activity,
        )

    return _build_log(activity, is_dry_run=False)


# --------------------------------------------------------------------------- #
# Transport implementations                                                    #
# --------------------------------------------------------------------------- #

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
            "authority": ms_authority,
        },
        passphrase=passphrase,
    )

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
        client.send(**kwargs)
        activity.append(
            f"Sent via MS Auth to {', '.join(batch.email_list)} with attachment {batch.zip_path}\n"
            f"Subject: {subject}\nBody:\n{body}"
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
        client.send(**report_kwargs)


def _send_via_smtp(
    batches: List[ClientBatch],
    *,
    smtp_conf: SMTPConfig,
    subject_template: str,
    body_template: str,
    sender_name: str,
    period: str,
    reporter_emails: list[str],
    activity: list[str],
) -> None:
    with smtplib.SMTP(smtp_conf.host, smtp_conf.port) as server:
        server.ehlo_or_helo_if_needed()

        if smtp_conf.use_tls:
            if server.has_extn("starttls"):
                server.starttls()
                server.ehlo()
            else:
                raise smtplib.SMTPNotSupportedError(
                    "SMTP server does not advertise STARTTLS; check host/port or disable use_tls."
                )

        if smtp_conf.username:
            if not server.has_extn("auth"):
                raise smtplib.SMTPNotSupportedError(
                    "SMTP AUTH not supported by server; enable TLS for providers like Gmail or remove credentials."
                )
            server.login(smtp_conf.username, smtp_conf.password)

        for batch in batches:
            msg = build_email(
                batch, smtp_conf.from_addr, subject_template, body_template, sender_name, period
            )
            server.send_message(msg)
            subject, body = _render_templates(batch, subject_template, body_template, sender_name, period)
            activity.append(
                f"Sent to {', '.join(batch.email_list)} with attachment {batch.zip_path}\n"
                f"Subject: {subject}\nBody:\n{body}"
            )

        if reporter_emails and activity:
            log_text = "\n".join(activity)
            report = EmailMessage()
            report["From"] = smtp_conf.from_addr
            report["To"] = ", ".join(reporter_emails)
            report["Subject"] = f"Invoice mailer report for {period}"
            report.set_content(log_text)
            server.send_message(report)
