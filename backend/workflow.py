
import os
import sqlite3
from pathlib import Path
from datetime import datetime
from config import (
    load_env_if_present,
    load_config,
    get_invoice_folder,
    get_soa_folder,
    get_client_directory,
    get_file_regex,
    get_packaging,
)
from db.db_path import get_db_path
from db.db import (
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
from utility import extract_pdf_text
from utility.read_xlsx import iter_xlsx_rows_as_dicts
from utility.packaging import collect_files_to_zip
from utility.email import ClientBatch, SMTPConfig, send_all_emails
from utility.key_mgmt import get_or_prompt_secret, delete_secret


def parse_recipients(raw: str | None) -> list[str]:
    """
    Parse comma- or newline-separated recipient list from config.
    """
    if not raw:
        return []
    recipients: list[str] = []
    for line in raw.splitlines():
        for piece in line.split(","):
            email = piece.strip()
            if email:
                recipients.append(email)
    return recipients


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


def db_mgmt(client_directory:Path,invoice_folder:Path,soa_folder:Path,inv_file_regex,soa_file_regex):

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

def prep_invoice_zips(client_list:list,period_str:str,agg:str):
    
    email_shipment = []

    for client in client_list:
        soa = get_soa_by_head_office(client)[0]
        head_office_name = soa['head_office_name']
        soa_file_path = soa['soa_file_path']

        invoices = get_invoices(**{agg:client},period_month=period_str)
        files_to_zip_paths = [inv['inv_file_path'] for inv in invoices]
        files_to_zip_paths.append(soa_file_path)
        zip_path = get_db_path().parent / f'{client}.zip'
        zip_path = collect_files_to_zip(files_to_zip_paths,zip_path)
        email_list = get_client_email(**{agg:client})
        email_shipment.append(
            {
                'zip_path':zip_path,
                'email_list':email_list,
                'head_office_name':head_office_name
            }
        )
    return email_shipment

def prep_and_send_emails(cfg,email_shipment, period_str:str, change_report:str | None):
    smtp_username = cfg["smtp"].get("username", "invoicemailer")
    smtp_password = cfg["smtp"].get("password", "")
    if not smtp_password:
        smtp_password = get_or_prompt_secret(
            "smtp_password",
            username=smtp_username or "invoicemailer",
            prompt=f"Enter SMTP password for {smtp_username or 'invoicemailer'}: ",
        )

    client_batches = [ClientBatch(
        zip_path=Path(r["zip_path"]),
        email_list=r["email_list"],
        head_office_name=r["head_office_name"],
    ) for r in email_shipment]

    smtp_cfg = SMTPConfig(
        host=cfg['smtp']['host'],
        port=cfg['smtp']['port'],
        username=smtp_username,
        password=smtp_password,
        use_tls=cfg.getboolean('smtp','use_tls',fallback=True),
        from_addr=cfg['smtp']['from_address'],
    )

    reporter_raw = cfg['email'].get('reporter_emails') or cfg['email'].get('reporter_email')

    email_template_kwargs = {
        'subject_template': cfg['email']['subject_template'],
        'body_template': cfg['email']['body_template'],
        'sender_name': cfg['email']['sender_name'],
        'period': period_str,
        'reporter_emails': parse_recipients(reporter_raw),
    }

    send_all_emails(client_batches,smtp_cfg,change_report,dry_run=False,**email_template_kwargs)

def run_workflow():
    load_env_if_present()
    cfg = load_config()

    invoice_folder = get_invoice_folder(cfg)
    soa_folder = get_soa_folder(cfg)
    client_directory = get_client_directory(cfg)
    inv_file_regex = get_file_regex(cfg,'inv')
    soa_file_regex = get_file_regex(cfg,'soa')

    packaging = get_packaging(cfg)
    agg = packaging['agg']

    period_month = datetime.now().month - 1 or 12
    period_year = datetime.now().year if period_month != 12 else datetime.now().year - 1
    period_str = f"{period_year}-{period_month:02d}"

    change_report = db_mgmt(
        client_directory,
        invoice_folder,
        soa_folder,
        inv_file_regex,
        soa_file_regex
    )
    client_list = get_client_list(agg)

    email_shipment = prep_invoice_zips(
        client_list,
        period_str,
        agg
    )
    prep_and_send_emails(cfg,email_shipment,period_str, change_report)



if __name__ == "__main__":
    run_workflow()
