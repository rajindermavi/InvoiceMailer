
import sqlite3
from pathlib import Path
from backend.config import (
    get_file_regex
)
from backend.db.db_path import get_db_path
from backend.db.db import (
    init_db,
    add_or_update_client,
    add_or_update_soa,
    record_invoice,
)
from backend.utility.extract_pdf_text import extract_pdf_date
from backend.utility.read_xlsx import iter_xlsx_rows_as_dicts


_db_built_this_session = False


def _load_keys(path: Path, table: str, key_cols: tuple[str, ...]) -> set[tuple]:
    """
    Load a set of key tuples from the given SQLite DB/table.
    """
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(f"SELECT {', '.join(key_cols)} FROM {table};")
        return {tuple(row[col] for col in key_cols) for row in cur.fetchall()}

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
        "Document Collection Updated – added/removed:"
        f" clients (+{len(new_keys['clients'] - old_keys['clients'])}"
        f"/-{len(old_keys['clients'] - new_keys['clients'])}),"
        f" invoices (+{len(new_keys['invoices'] - old_keys['invoices'])}"
        f"/-{len(old_keys['invoices'] - new_keys['invoices'])}),"
        f" soa (+{len(new_keys['soa'] - old_keys['soa'])}"
        f"/-{len(old_keys['soa'] - new_keys['soa'])})"
    )
    old_db_path.unlink(missing_ok=True)
    return report

def backup_existing_db(db_path: Path):
    empty = {"clients": set(), "invoices": set(), "soa": set()}
    if not db_path.exists():
        return None, empty

    suffix = ".bak"
    candidate = db_path.with_suffix(db_path.suffix + suffix)
    n = 1
    while candidate.exists():
        candidate = db_path.with_suffix(db_path.suffix + f"{suffix}{n}")
        n += 1

    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as src, sqlite3.connect(candidate) as dst:
        src.backup(dst)

    old_keys = {
        "clients": _load_keys(candidate, "clients", ("customer_number",)),
        "invoices": _load_keys(candidate, "invoices", ("tax_invoice_no",)),
        "soa": _load_keys(candidate, "soa", ("soa_file_path",)),
    }
    return candidate, old_keys


def mark_db_dirty():
    """
    Allow the next db_mgmt call to rebuild by clearing the session guard.
    """
    global _db_built_this_session
    _db_built_this_session = False


def db_mgmt(client_directory: Path, invoice_folder: Path, soa_folder: Path, *, force: bool = False):
    global _db_built_this_session
    inv_file_regex = get_file_regex('invoice')
    soa_file_regex = get_file_regex('soa')

    db_path = get_db_path()

    if _db_built_this_session and db_path.exists() and not force:
        return "Database already built this session; reusing existing snapshot."
    _db_built_this_session = True

    try:
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
            invoice_date = extract_pdf_date(inv_file_path,field = 'inv_date')
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
            soa_date = extract_pdf_date(soa_file_path,'soa_date')
            soa_period_month = soa_date.rsplit('-',1)[0]
            add_or_update_soa(
                head_office,
                head_office_name,
                soa_file_path,
                soa_date,
                soa_period_month
            )

        return report_and_cleanup_old_db(old_db_path, old_keys, db_path)
    except Exception:
        _db_built_this_session = False
        raise
