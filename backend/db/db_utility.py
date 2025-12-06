
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



def db_mgmt(client_directory: Path, invoice_folder: Path, soa_folder: Path, *, force: bool = False):

    inv_file_regex = get_file_regex('invoice')
    soa_file_regex = get_file_regex('soa')

    db_path = get_db_path()

    try:
        db_path.unlink()

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

    except Exception:
        raise
