
from pathlib import Path
import re
from backend.db.db_utility import db_mgmt
from backend.db.db_path import get_db_path
from backend.db.db import (
    get_client_list,
    get_client,
    get_invoices,
    get_client_email,
    get_soa_by_head_office
)
from backend.utility.packaging import collect_files_to_zip
from backend.utility.email import ClientBatch, SMTPConfig, send_all_emails





def scan_for_invoices(client_list:list,period_str:str,agg:str):
    invoices_to_ship: dict[str, list[dict[str, str | None]]] = {}

    for client in client_list:

        kwargs = {agg: client}

        client_rows = get_client(**kwargs)
        head_office = client_rows[0]['head_office']
        soa_rows = get_soa_by_head_office(head_office=head_office)
        soa_path = soa_rows[0]["soa_file_path"] if soa_rows else None
        head_office_name = soa_rows[0]["head_office_name"] if soa_rows else None

        invoices = get_invoices(**{agg: client}, period_month=period_str)
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
):
    email_shipment = []
    base_zip_dir = Path(zip_output_dir) if zip_output_dir else get_db_path().parent
    base_zip_dir.mkdir(parents=True, exist_ok=True)

    for head_office, invoices in invoices_to_ship.items():
        if not invoices:
            continue

        raw_head_office_name = invoices[0].get("head_office_name")
        head_office_name = raw_head_office_name or head_office or "client"
        # Sanitize for Windows-safe usage and include the aggregate key to reduce collisions.
        head_office_name = re.sub(r'[<>:"/\\\\|?*]+', "_", head_office_name).strip().strip(".")
        if head_office and head_office not in head_office_name:
            head_office_name = f"{head_office_name}_{head_office}"
        soa_path = invoices[0].get("soa_path")

        files_to_zip_paths = [inv["invoice_path"] for inv in invoices if inv.get("invoice_path")]
        if soa_path:
            files_to_zip_paths.append(soa_path)

        if not files_to_zip_paths:
            continue

        zip_path = collect_files_to_zip(files_to_zip_paths, base_zip_dir / f"{head_office}.zip")

        email_list = get_client_email(head_office=head_office)
        email_shipment.append(
            {
                "zip_path": zip_path,
                "email_list": email_list,
                "head_office_name": head_office_name,
            }
        )

    return email_shipment

def prep_and_send_emails(
    smtp_config,
    email_setup,
    email_shipment,
    period_str: str,
    change_report: str | None,
    dry_run: bool = False,
):
    smtp_username = smtp_config.get('username', "")
    smtp_password = smtp_config.get('password', "")

    client_batches = [ClientBatch(
        zip_path=Path(es.get("zip_path")),
        email_list=es.get("email_list"),
        head_office_name=es.get("head_office_name"),
    ) for es in email_shipment]

    smtp_cfg = SMTPConfig(
        host=smtp_config['host'],
        port=smtp_config['port'],
        username=smtp_username,
        password=smtp_password,
        use_tls=smtp_config.get('use_tls', True),
        from_addr=smtp_config['from_addr'],
    )

    email_template_kwargs = {
        'subject_template': email_setup.get('subject_template',''),
        'body_template': email_setup.get('body_template',''),
        'sender_name': email_setup.get('sender_name',''),
        'period': period_str,
        'reporter_emails': email_setup.get('reporter_emails',[]),
    }

    email_report = send_all_emails(
        client_batches,
        smtp_cfg,
        change_report,
        dry_run=dry_run,
        **email_template_kwargs,
    )
    if email_report is None and dry_run:
        email_report = "Dry run complete; emails were prepared but not sent."
    return email_report

def run_workflow(
        invoice_folder: Path | None = None,
        soa_folder: Path | None = None,
        client_directory: Path | None = None,
        zip_output_dir: Path | None = None,
        agg: str = "head_office",
        period_month: int | str | None = None,
        period_year: int | str | None = None,
        smtp_config: dict | None = None,
        email_setup: dict | None = None,
        dry_run: bool | None = None,
        mode: str | None = None,
):
    change_report = db_mgmt(
        client_directory,
        invoice_folder,
        soa_folder
    )

    if period_month is None or period_year is None:
        raise ValueError("period_month and period_year are required when sending emails.")

    period_month = int(period_month)
    period_year = int(period_year)
    period_str = f"{period_year}-{period_month:02d}"
    resolved_dry_run = dry_run
    if resolved_dry_run is None:
        resolved_dry_run = (mode or "").lower() == "test"

    client_list = get_client_list(agg)

    invoices_to_ship = scan_for_invoices(client_list, period_str, agg)
    email_shipment = prep_invoice_zips(invoices_to_ship, zip_output_dir)
    email_report = prep_and_send_emails(
        smtp_config,
        email_setup,
        email_shipment,
        period_str,
        change_report,
        dry_run=resolved_dry_run,
    )
    return {"change_report": change_report,'email_report': email_report}



if __name__ == "__main__":
    run_workflow()
