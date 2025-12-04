
# Invoice Mailer

InvoiceMailer ingests invoice PDFs, SOA PDFs, and a client list Excel file, normalizes them into a local SQLite database, zips per-client document bundles, and delivers them over SMTP with configurable email templates. The GUI (`app.py` → `gui/app_gui.py`) wraps the workflow; `backend/workflow.py` is the orchestration layer used by the Scan, Zip, and Send tabs.

## How documents are discovered and committed
- **Client list (Excel/CSV):** Parsed with `backend.utility.read_xlsx.iter_xlsx_rows_as_dicts`. Expected headers include `Head Office`, `Customer Number`, and up to five recipient columns named `emailforinvoice1`…`emailforinvoice5`. Each row is upserted via `backend.db.db.add_or_update_client`, keeping one row per `customer_number`.
- **Invoice PDFs:** Searched recursively under the configured invoice folder with `Path.rglob('*invoice*.pdf', case_sensitive=False)`. Filenames must match the `invoice` regex from `backend.config.file_patterns` (default: `<customer> invoice <invoice_no> <ship>.pdf`). Dates are read from a configured PDF rectangle (see `backend.config.pdf_rect_settings['inv_date']`) using PyMuPDF, with optional OCR fallback. Each match becomes a row in `invoices` (`tax_invoice_no`, `customer_number`, `ship_name`, `inv_file_path`, `invoice_date`, `inv_period_month`) via `record_invoice`.
- **SOA PDFs:** Searched recursively under the SOA folder for `Statement*.pdf` and parsed with the `soa` regex (`Statement of Account for- <head_office> <head_office_name>.PDF`). Dates come from `pdf_rect_settings['soa_date']`. Each file is stored with `add_or_update_soa` (`head_office`, `head_office_name`, `soa_file_path`, `soa_date`, `soa_period_month`).
- **Database lifecycle:** `db_mgmt` backs up any existing SQLite file (to `*.bak`), rebuilds the schema (`clients`, `invoices`, `soa`), re-imports from disk, then reports row deltas before deleting the backup. DB location is resolved in `backend.db.db_path` (dev: `backend/db/data/invoice_mailer.sqlite3`; prod: per-user app data; overridable via `APP_DB_PATH`).

## Creating custom emails per client
- Email content is template-driven (`backend.utility.email.build_email`). Placeholders: `{head_office_name}`, `{contact_name}`, `{sender_name}`, `{month_year}`, `{period}`, `{month}`, `{year}`. Templates are pulled from saved settings (GUI Email tab) with defaults from `gui/utility.py`.
- Each client batch (`ClientBatch`) is built from the ZIP output: one ZIP per head office/customer containing that client’s invoices plus the optional SOA. Recipients are aggregated from the client list (`get_client_email`), supporting up to five addresses per client.
- A per-run report (`reporter_emails`) can be sent summarizing send activity and any DB change report.

## Saving settings as secure secrets
- Settings (paths, SMTP host/port/credentials, mode, email templates, reporter list, target month/year) are persisted through `backend.config.SecureConfig`.
- Storage is environment-aware: development writes alongside the project; production writes under `%LOCALAPPDATA%/InvoiceMailer` on Windows or `~/.invoicemailer` elsewhere.
- Encryption uses DPAPI on Windows production when available; otherwise Fernet with a generated key stored next to the encrypted JSON (`config.enc` + `encryption.key`). All values, including SMTP password, are stored encrypted at rest.

## Scan for invoices process
- Triggered from the Scan tab or via `scan_for_invoices`. Steps:
  1. Run `db_mgmt` to rebuild and refresh the DB from disk.
  2. Require `period_month`/`period_year`; compute `period_str` (`YYYY-MM`).
  3. Get the target client list (`get_client_list`) using the selected aggregate key (`head_office` or `customer_number`).
  4. For each client, fetch invoices matching the period and join the matching SOA for the client’s head office.
  5. Present a flattened table of invoice metadata plus matched file stems; show the DB change report.

## Zip invoices
- `prep_invoice_zips` builds one ZIP per client aggregate (typically head office). Each ZIP includes all matched invoice PDFs for that client and the client’s SOA if present.
- Output folder defaults to the DB directory; override with the ZIP Output setting. Filenames use the aggregate key (`<head_office>.zip`).
- The resulting shipment metadata (`zip_path`, `email_list`, `head_office_name`) is cached for the Send step.

## Send invoices by SMTP
- `prep_and_send_emails` converts shipments into `EmailMessage` objects, attaches the ZIP, and delivers via `smtplib.SMTP`.
- TLS/STARTTLS is enforced when `use_tls` is true; optional login uses the provided `username`/`password`. The `from_addr` populates the From header.
- In Test mode (`mode = "Test"` or `dry_run=True`), the system builds messages and a human-readable activity log without touching the network. In Active mode, each batch is sent and logged; failures surface via exceptions and the GUI log pane.

## Schema snapshot
- `clients(customer_number UNIQUE, head_office, emailforinvoice1..5)`
- `invoices(tax_invoice_no UNIQUE, inv_file_path UNIQUE, customer_number, ship_name, invoice_date, inv_period_month, sent flags)`
- `soa(soa_file_path UNIQUE, head_office, head_office_name, soa_date, soa_period_month, sent flags)`
