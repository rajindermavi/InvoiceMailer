
import os
import sqlite3
from pathlib import Path
from datetime import datetime
from backend.config import (
    get_file_regex,
    get_date_regex
)
from backend.db.db_path import get_db_path
from backend.db.db import (
    init_db,
    add_or_update_client,
    add_or_update_soa,
    record_invoice,
    mark_invoice_sent,
    get_client_list,
    get_client,
    get_invoices,
    get_client_email,
    get_soa_by_head_office
)
from backend.utility import extract_pdf_text
from backend.utility.read_xlsx import iter_xlsx_rows_as_dicts
from backend.utility.packaging import collect_files_to_zip
from backend.utility.email import ClientBatch, SMTPConfig, send_all_emails


def _load_keys(path: Path, table: str, key_cols: tuple[str, ...]) -> set[tuple]:
    """
    Load a set of key tuples from the given SQLite DB/table.
    """
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(f"SELECT {', '.join(key_cols)} FROM {table};")
        return {tuple(row[col] for col in key_cols) for row in cur.fetchall()}


def backup_existing_db(db_path: Path):
    """
    If a DB already exists, move it aside and return the backup path + key snapshot.
    """
    if not db_path.exists():
        return None, {"clients": set(), "invoices": set(), "soa": set()}

    suffix = ".bak"
    candidate = db_path.with_suffix(db_path.suffix + suffix)
    counter = 1
    while candidate.exists():
        candidate = db_path.with_suffix(db_path.suffix + f"{suffix}{counter}")
        counter += 1
    db_path.rename(candidate)

    old_keys = {
        "clients": _load_keys(candidate, "clients", ("customer_number",)),
        "invoices": _load_keys(candidate, "invoices", ("tax_invoice_no",)),
        "soa": _load_keys(candidate, "soa", ("soa_file_path",)),
    }
    return candidate, old_keys


def report_and_cleanup_old_db(old_db_path: Path | None, old_keys: dict[str, set], db_path: Path):
    """
    Report diff between new and old DB snapshots, then delete the backup.
    """
    if not old_db_path or not old_db_path.exists():
        return

    new_keys = {
        "clients": _load_keys(db_path, "clients", ("customer_number",)),
        "invoices": _load_keys(db_path, "invoices", ("tax_invoice_no",)),
        "soa": _load_keys(db_path, "soa", ("soa_file_path",)),
    }
    report = (
        "DB diff – added/removed:"
        f" clients (+{len(new_keys['clients'] - old_keys['clients'])}"
        f"/-{len(old_keys['clients'] - new_keys['clients'])}),"
        f" invoices (+{len(new_keys['invoices'] - old_keys['invoices'])}"
        f"/-{len(old_keys['invoices'] - new_keys['invoices'])}),"
        f" soa (+{len(new_keys['soa'] - old_keys['soa'])}"
        f"/-{len(old_keys['soa'] - new_keys['soa'])})"
    )
    old_db_path.unlink(missing_ok=True)
    return report


def db_mgmt(client_directory:Path,invoice_folder:Path,soa_folder:Path):

    inv_file_regex = get_file_regex('invoice')
    soa_file_regex = get_file_regex('soa')

    db_path = get_db_path()
    old_db_path, old_keys = backup_existing_db(db_path)

    # CREATE NEW DB
    init_db()
    

    for row in iter_xlsx_rows_as_dicts(client_directory):
        head_office = row.get('Head Office','')
        customer_number = row.get('Customer Number')
        emails = [row.get(f'emailforinvoice{idx}') for idx in range(1,6) if row.get(f'emailforinvoice{idx}')]
        add_or_update_client(head_office,customer_number,emails)

    for file in invoice_folder.rglob('*invoice*.pdf',case_sensitive=False):

        m = inv_file_regex.match(file.name)
        if not m:
            continue
        customer_number = m.group(1)
        tax_invoice_no = m.group(2)
        ship_name = m.group(3)
        inv_file_path = file.as_posix()    
        invoice_date = extract_pdf_text.extract_pdf_date(inv_file_path,field = 'inv_date')
        inv_period_month = invoice_date.rsplit('-',1)[0]
        record_invoice(
            tax_invoice_no,
            customer_number,
            ship_name,
            inv_file_path,
            invoice_date,
            inv_period_month
        )

    for file in soa_folder.rglob('Statement*.pdf',case_sensitive=False):

        m = soa_file_regex.match(file.name)
        if not m:
            print('not m')
            continue
        head_office = m.group(1)
        head_office_name = m.group(2)
        soa_file_path = file.as_posix()
        soa_date = extract_pdf_text.extract_pdf_date(soa_file_path,'soa_date')
        soa_period_month = soa_date.rsplit('-',1)[0]
        add_or_update_soa(
            head_office,
            head_office_name,
            soa_file_path,
            soa_date,
            soa_period_month
        )

    return report_and_cleanup_old_db(old_db_path, old_keys, db_path)

def scan_for_invoices(client_list:list,period_str:str,agg:str):
    invoices_to_ship: dict[str, list[dict[str, str | None]]] = {}

    for client in client_list:
        head_office = client
        if agg == "customer_number":
            client_rows = get_client(customer_number=client)
            head_office = client_rows[0]["head_office"] if client_rows else client

        soa_rows = get_soa_by_head_office(head_office, period_month=period_str)
        head_office_name = soa_rows[0]["head_office_name"] if soa_rows else None
        soa_path = soa_rows[0]["soa_file_path"] if soa_rows else None

        invoices = get_invoices(**{agg: client}, period_month=period_str)
        invoices_to_ship[head_office] = [
            {
                "ship_name": inv["ship_name"],
                "invoice_number": inv["tax_invoice_no"],
                "invoice_date": inv["invoice_date"],
                "invoice_path": inv["inv_file_path"],
                "soa_path": soa_path,
                "head_office_name": head_office_name,
            }
            for inv in invoices
        ]

    return invoices_to_ship

def prep_invoice_zips(client_list:list,period_str:str,agg:str):
    invoices_to_ship = scan_for_invoices(client_list, period_str, agg)
    email_shipment = []

    for head_office, invoices in invoices_to_ship.items():
        if not invoices:
            continue

        head_office_name = invoices[0].get("head_office_name")
        soa_path = invoices[0].get("soa_path")

        files_to_zip_paths = [inv["invoice_path"] for inv in invoices if inv.get("invoice_path")]
        if soa_path:
            files_to_zip_paths.append(soa_path)

        if not files_to_zip_paths:
            continue

        zip_path = get_db_path().parent / f"{head_office}.zip"
        zip_path = collect_files_to_zip(files_to_zip_paths, zip_path)

        email_list = get_client_email(head_office=head_office)
        email_shipment.append(
            {
                "zip_path": zip_path,
                "email_list": email_list,
                "head_office_name": head_office_name,
            }
        )

    return email_shipment

def prep_and_send_emails(smtp_config,email_setup,email_shipment, period_str:str, change_report:str | None):
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

    send_all_emails(client_batches,smtp_cfg,change_report,dry_run=False,**email_template_kwargs)

def run_workflow(
        invoice_folder: Path | None = None,
        soa_folder: Path | None = None,
        client_directory: Path | None = None,
        agg: str = "head_office",
        period_month: int | str | None = None,
        period_year: int | str | None = None,
        smtp_config: dict | None = None,
        email_setup: dict | None = None,
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

    client_list = get_client_list(agg)

    email_shipment = prep_invoice_zips(
        client_list,
        period_str,
        agg
    )
    prep_and_send_emails(smtp_config,email_setup,email_shipment,period_str, change_report)
    return {"change_report": change_report}



if __name__ == "__main__":
    run_workflow()
