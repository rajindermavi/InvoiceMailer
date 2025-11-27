import smtplib
from email.message import EmailMessage
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

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


def build_email(batch: ClientBatch,
                smtp_conf: SMTPConfig,
                subject_template,
                body_template,
                sender_name,
                period) -> EmailMessage:
    # Allow config values that use escaped newlines (e.g., "\\n") to render properly.
    if isinstance(body_template, str):
        body_template = body_template.replace("\\n", "\n")
    if isinstance(subject_template, str):
        subject_template = subject_template.replace("\\n", "\n")

    msg = EmailMessage()

    # Headers
    msg["From"] = smtp_conf.from_addr
    msg["To"] = ", ".join(batch.email_list)  # all recipients for this client
    msg["Subject"] = subject_template.format(
        month_year=period,
    )

    # Body
    body = body_template.format(
        contact_name=batch.head_office_name,
        sender_name=sender_name,
        month_year=period,
    )
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
    smtp_conf: SMTPConfig,
    change_report: Optional[str] = None,
    dry_run: bool = False,
    subject_template: str = DEFAULT_SUBJECT_TEMPLATE,
    body_template: str = DEFAULT_BODY_TEMPLATE,
    sender_name: str = "Your Company",  
    period: str = "last month",
    reporter_emails: Optional[List[str]] = None,
) -> None:
    reporter_emails = reporter_emails or []

    def _get_body_text(msg: EmailMessage) -> str:
        body_part = msg.get_body(preferencelist=("plain",))
        return body_part.get_content() if body_part else ""

    def _activity_entry(prefix: str, batch: ClientBatch, msg: EmailMessage) -> str:
        return (
            f"{prefix} {', '.join(batch.email_list)} with attachment {batch.zip_path}\n"
            f"Subject: {msg['Subject']}\n"
            f"Body:\n{_get_body_text(msg)}"
        )

    if dry_run:
        # No network calls, just a sanity check
        for batch in batches:
            
            msg = build_email(batch, smtp_conf, subject_template, body_template, sender_name, period)
            print(
                f"[DRY RUN] Would send to {batch.email_list} "
                f"with attachment {batch.zip_path}"
            )
            print(msg.get_body())  #
        return

    activity_log: List[str] = []

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
            msg = build_email(batch, smtp_conf, subject_template, body_template, sender_name, period)
            server.send_message(msg)
            print(f"Sent email to {batch.email_list} with {batch.zip_path}")
            activity_log.append(_activity_entry("Sent to", batch, msg))

        sep = "\n" + ("-" * 40) + "\n"
        activity_log = f"Email sending activity for period: {period}" + sep.join(activity_log) + sep + (
            f"\nChange Report:\n{change_report}\n" if change_report else "" 
        )

        if reporter_emails and activity_log:
            report = EmailMessage()
            report["From"] = smtp_conf.from_addr
            report["To"] = ", ".join(reporter_emails)
            report["Subject"] = f"Invoice mailer report for {period}"
            report.set_content(activity_log)
            server.send_message(report)
            print(f"Sent activity report to {reporter_emails}")
