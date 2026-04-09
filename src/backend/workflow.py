
import logging
from pathlib import Path
import re

logger = logging.getLogger(__name__)
from src.backend.db.db_path import get_db_path
from src.backend.db.db import (
    get_client,
    get_invoices,
    get_client_email,
    get_soa_by_head_office
)
from src.backend.utility.packaging import collect_files_to_zip
from src.backend.utility.send import ClientBatch, SMTPConfig, send_all_emails





_VALID_AGG = {"head_office", "customer_number"}


def scan_for_invoices(
    client_list: list,
    period_year: int | str,
    period_month: int | str,
    agg: str,
):
    if agg not in _VALID_AGG:
        raise ValueError(f"agg must be 'head_office' or 'customer_number', got {agg!r}")
    base_year = int(period_year)
    base_month = int(period_month)
    period_str = f"{base_year}-{base_month:02d}"
    next_month = 1 if base_month == 12 else base_month + 1
    next_year = base_year + 1 if base_month == 12 else base_year
    next_period_str = f"{next_year}-{next_month:02d}"
    invoices_to_ship: dict[str, list[dict[str, str | None]]] = {}

    for client in client_list:

        kwargs = {agg: client}

        client_rows = get_client(**kwargs)
        if not client_rows:
            raise ValueError(f"Client not found in database: {client!r}")
        head_office = client_rows[0]['head_office']
        soa_rows = get_soa_by_head_office(head_office=head_office)
        soa_path = soa_rows[0]["soa_file_path"] if soa_rows else None
        head_office_name = soa_rows[0]["head_office_name"] if soa_rows else None

        invoices = get_invoices(**{agg: client}, period_month=period_str)
        invoices += get_invoices(**{agg: client}, period_month=next_period_str)
        invoices_to_ship[client] = [
            {
                "head_office_name": head_office_name,
                "ship_name": inv["ship_name"],
                "invoice_number": inv["tax_invoice_no"],
                "invoice_date": inv["invoice_date"],
                "invoice_path": inv["inv_file_path"],
                "soa_path": soa_path,
                "customer_number": inv["customer_number"],
            }
            for inv in invoices
        ]

    return invoices_to_ship

def prep_invoice_zips(
    invoices_to_ship: dict[str, list[dict[str, str | None]]],
    zip_output_dir: Path | str | None = None,
    agg: str = "head_office",
):
    email_shipment = []
    base_zip_dir = Path(zip_output_dir) if zip_output_dir else get_db_path().parent
    base_zip_dir.mkdir(parents=True, exist_ok=True)
    used_stems: set[str] = set()

    for client_key, invoices in invoices_to_ship.items():
        if not invoices:
            continue

        raw_head_office_name = invoices[0].get("head_office_name")
        head_office_name = raw_head_office_name or client_key or "client"
        # Sanitize for Windows-safe usage and include the aggregate key to reduce collisions.
        head_office_name = re.sub(r'[<>:"/\\\\|?*]+', "_", head_office_name).strip().strip(".")
        if client_key and client_key not in head_office_name:
            head_office_name = f"{head_office_name}_{client_key}"
        soa_path = invoices[0].get("soa_path")

        files_to_zip_paths = [inv["invoice_path"] for inv in invoices if inv.get("invoice_path")]
        if soa_path:
            files_to_zip_paths.append(soa_path)

        if not files_to_zip_paths:
            continue

        safe_stem = re.sub(r'[<>:"/\\|?*]+', "_", client_key).strip().strip(".")
        if safe_stem in used_stems:
            counter = 2
            while f"{safe_stem}_{counter}" in used_stems:
                counter += 1
            safe_stem = f"{safe_stem}_{counter}"
            logger.warning("ZIP filename collision for %r — writing as %s.zip", client_key, safe_stem)
        used_stems.add(safe_stem)

        zip_path = collect_files_to_zip(files_to_zip_paths, base_zip_dir / f"{safe_stem}.zip")

        email_list = get_client_email(**{agg: client_key})
        email_shipment.append(
            {
                "zip_path": zip_path,
                "email_list": email_list,
                "head_office_name": head_office_name,
            }
        )

    return email_shipment

def prep_and_send_emails(
    email_auth_method,
    smtp_config,
    ms_auth_config,
    email_setup,
    email_shipment,
    period_str: str,
    dry_run: bool = False,
    show_message=None,
    passphrase=None,
):
    client_batches = [ClientBatch(
        zip_path=Path(es.get("zip_path")),
        email_list=es.get("email_list"),
        head_office_name=es.get("head_office_name"),
    ) for es in email_shipment]

    smtp_cfg = SMTPConfig(
        host=smtp_config['host'],
        port=smtp_config['port'],
        username=smtp_config.get('username', ""),
        password=smtp_config.get('password', ""),
        use_tls=smtp_config.get('use_tls', True),
        from_addr=smtp_config['from_addr'],
    )

    email_report = send_all_emails(
        client_batches,
        email_auth_method,
        smtp_cfg,
        ms_email_address=ms_auth_config.get('ms_email_address', "") if ms_auth_config else "",
        ms_authority=ms_auth_config.get('ms_authority', "organizations") if ms_auth_config else "organizations",
        ms_client_id=ms_auth_config.get('ms_client_id', "") if ms_auth_config else "",
        dry_run=dry_run,
        subject_template=email_setup.get('subject_template', ''),
        body_template=email_setup.get('body_template', ''),
        sender_name=email_setup.get('sender_name', ''),
        period=period_str,
        reporter_emails=email_setup.get('reporter_emails', []),
        show_message=show_message,
        passphrase=passphrase,
    )
    return email_report
