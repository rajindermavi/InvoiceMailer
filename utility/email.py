import smtplib
from email.message import EmailMessage
from dataclasses import dataclass
from pathlib import Path
from typing import List

SUBJECT_TEMPLATE = "Monthly invoices for {head_office_name}"
BODY_TEMPLATE = """Dear {head_office_name} team,

Please find attached the invoice archive for this period.

If you have any questions or notice any discrepancies, please reply to this email.

Best regards,
Your Accounts Team
"""

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
                subject_template: str = SUBJECT_TEMPLATE,
                body_template: str = BODY_TEMPLATE) -> EmailMessage:
    msg = EmailMessage()

    # Headers
    msg["From"] = smtp_conf.from_addr
    msg["To"] = ", ".join(batch.email_list)  # all recipients for this client
    msg["Subject"] = subject_template.format(
        head_office_name=batch.head_office_name
    )

    # Body
    body = body_template.format(
        head_office_name=batch.head_office_name
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
    dry_run: bool = False,
) -> None:
    if dry_run:
        # No network calls, just a sanity check
        for batch in batches:
            print(
                f"[DRY RUN] Would send to {batch.email_list} "
                f"with attachment {batch.zip_path}"
            )
        return

    with smtplib.SMTP(smtp_conf.host, smtp_conf.port) as server:
        if smtp_conf.use_tls:
            server.starttls()

        if smtp_conf.username:
            server.login(smtp_conf.username, smtp_conf.password)

        for batch in batches:
            msg = build_email(batch, smtp_conf)
            server.send_message(msg)
            print(f"Sent email to {batch.email_list} with {batch.zip_path}")