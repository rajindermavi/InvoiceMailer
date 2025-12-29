import smtplib
from email.message import EmailMessage
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from gui.msal_device_code import send_email_via_graph

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
    host: str          # e.g. "smtp.gmail.com"
    port: int          # e.g. 587
    username: str
    password: str
    from_addr: str     # visible From: address
    use_tls: bool = True

@dataclass
class MSAuthConfig:
    host: str
    port: int
    starttls: str
    ms_email_address: str

def build_email(batch: ClientBatch,
                from_addr: str,
                subject_template,
                body_template,
                sender_name,
                period) -> EmailMessage:
    def _period_parts(period_str: str) -> tuple[str, str]:
        try:
            year, month = period_str.split("-", 1)
            return month, year
        except Exception:
            return "", ""

    month_val, year_val = _period_parts(str(period))

    # Allow config values that use escaped newlines (e.g., "\\n") to render properly.
    if isinstance(body_template, str):
        body_template = body_template.replace("\\n", "\n")
    if isinstance(subject_template, str):
        subject_template = subject_template.replace("\\n", "\n")

    msg = EmailMessage()

    # Headers
    msg["From"] = from_addr
    msg["To"] = ", ".join(batch.email_list)  # all recipients for this client

    fmt_values = {
        "head_office_name": batch.head_office_name,
        "contact_name": batch.head_office_name,
        "sender_name": sender_name,
        "month_year": period,
        "period": period,
        "month": month_val,
        "year": year_val,
    }

    msg["Subject"] = subject_template.format(**fmt_values)

    # Body
    body = body_template.format(**fmt_values)
    msg.set_content(body)

    # Attachment (the zip at batch.zip_path)
    zip_path = batch.zip_path

    # Pathlib works on Linux and Windows, just ensure paths are correct at runtime.
    with zip_path.open("rb") as f:
        file_data = f.read()

    msg.add_attachment(
        file_data,
        maintype="application",
        subtype="zip",
        filename=zip_path.name,
    )

    return msg

def send_all_emails(
    batches: List[ClientBatch],
    email_auth_method: str,
    smtp_conf: SMTPConfig,
    ms_auth_conf: Optional[Union[MSAuthConfig, dict]] = None,
    change_report: Optional[str] = None,
    dry_run: bool = False,
    subject_template: str = DEFAULT_SUBJECT_TEMPLATE,
    body_template: str = DEFAULT_BODY_TEMPLATE,
    sender_name: str = "Your Company",  
    period: str = "last month",
    reporter_emails: Optional[List[str]] = None,
    token_provider=None,
    secure_config=None,
) -> None:
    reporter_emails = reporter_emails or []
    auth_method = (email_auth_method or "smtp").lower()
    use_ms_auth = auth_method == "ms_auth"

    def _ms_email(cfg: Optional[Union[MSAuthConfig, dict]]) -> str:
        if isinstance(cfg, dict):
            return cfg.get("ms_email_address") or ""
        return getattr(cfg, "ms_email_address", "") if cfg else ""

    ms_email_address = _ms_email(ms_auth_conf)

    if not dry_run and use_ms_auth and not ms_email_address:
        raise ValueError("MS Auth email address is required when email_auth_method is 'ms_auth'.")

    def _get_body_text(msg: EmailMessage) -> str:
        body_part = msg.get_body(preferencelist=("plain",))
        return body_part.get_content() if body_part else ""

    def _activity_entry(prefix: str, batch: ClientBatch, msg: EmailMessage) -> str:
        return (
            f"{prefix} {', '.join(batch.email_list)} with attachment {batch.zip_path}\n"
            f"Subject: {msg['Subject']}\n"
            f"Body:\n{_get_body_text(msg)}"
        )

    def _build_activity_log(entries: List[str], is_dry_run: bool) -> str:
        sep = "\n" + ("-" * 40) + "\n"
        log_text = f"Email sending activity for period: {period}" + sep.join(entries) + sep
        if change_report:
            log_text += f"\nChange Report:\n{change_report}\n"
        if is_dry_run:
            # Clear markers make it obvious this was not a real send.
            log_text = f"<<<TEST ONLY DRY RUN>>>\n{log_text}\n<<<END TEST ONLY DRY RUN>>>"
        return log_text

    from_addr = ms_email_address if use_ms_auth and ms_email_address else smtp_conf.from_addr
    activity_log: List[str] = []

    if dry_run:
        # No network calls, just record what would have been sent.
        for batch in batches:
            msg = build_email(batch, from_addr, subject_template, body_template, sender_name, period)
            activity_log.append(_activity_entry("Would send to", batch, msg))
        return _build_activity_log(activity_log, is_dry_run=True)

    if use_ms_auth:
        for batch in batches:
            msg = build_email(batch, from_addr, subject_template, body_template, sender_name, period)
            send_email_via_graph(
                ms_auth_conf or {},
                msg,
                token_provider=token_provider,
                interactive=False,
                secure_config=secure_config,
            )
            activity_log.append(_activity_entry("Sent via MS Auth to", batch, msg))

        activity_log = _build_activity_log(activity_log, is_dry_run=False)

        if reporter_emails and activity_log:
            report = EmailMessage()
            report["From"] = from_addr
            report["To"] = ", ".join(reporter_emails)
            report["Subject"] = f"Invoice mailer report for {period}"
            report.set_content(activity_log)
            send_email_via_graph(
                ms_auth_conf or {},
                report,
                token_provider=token_provider,
                interactive=False,
                secure_config=secure_config,
            )
            print(f"Sent activity report to {reporter_emails}")
        return activity_log

    with smtplib.SMTP(smtp_conf.host, smtp_conf.port) as server:
        # Advertised capabilities are only available after EHLO.
        server.ehlo_or_helo_if_needed()

        if smtp_conf.use_tls:
            if server.has_extn("starttls"):
                server.starttls()
                server.ehlo()  # refresh capabilities after TLS handshake
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
            msg = build_email(batch, smtp_conf.from_addr, subject_template, body_template, sender_name, period)
            server.send_message(msg)
            print(f"Sent email to {batch.email_list} with {batch.zip_path}")
            activity_log.append(_activity_entry("Sent to", batch, msg))

        activity_log = _build_activity_log(activity_log, is_dry_run=False)

        if reporter_emails and activity_log:
            report = EmailMessage()
            report["From"] = smtp_conf.from_addr
            report["To"] = ", ".join(reporter_emails)
            report["Subject"] = f"Invoice mailer report for {period}"
            report.set_content(activity_log)
            server.send_message(report)
            print(f"Sent activity report to {reporter_emails}")
    return activity_log
