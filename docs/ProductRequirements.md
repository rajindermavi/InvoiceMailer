# Goal

Automate monthly/on-demand invoice emailing. Match each invoice to a head office, zip invoices per head office along with the corresponding monthly statement of account, and email all concerned parties.

# Inputs

The program requires 3 sources of data.

* **Customer list** — `.xlsx` file with columns: Head Office, Customer Number, and up to 5 email addresses per customer (`emailforinvoice1`–`emailforinvoice5`)
* **Invoices** — PDF files, one per customer shipment, following the naming convention: `{CustomerNumber} invoice {InvoiceNumber} {ShipName}.pdf`
* **Statements of Account (SOA)** — PDF files, one per head office, following the naming convention: `Statement of Account for- {HeadOfficeCode} {HeadOfficeName}.PDF`

# High Level Workflow

1. **Settings** — Ops configures source folders, email credentials, and billing period
2. **Scan** — The app rebuilds the database from source files and matches invoices and SOAs to customers
3. **Zip** — Matched invoices and SOAs are bundled into one ZIP per head office (or per customer)
4. **Send** — ZIP files are emailed to each head office's recipients; a run report is sent to internal reporters

# Primary User Stories

* Ops selects invoice folder, SOA folder, customer list file, and ZIP output folder via a settings UI
* Ops selects the billing month and year; the system automatically also retrieves invoices from the following month to catch cross-month-boundary billing periods
* Ops chooses whether to aggregate invoices by head office (one ZIP per head office) or by individual customer number
* Upon scan, invoices, SOAs, and the customer list are parsed and recorded into a local SQLite database
* Scan results are displayed in a table showing each matched invoice with its customer, ship name, invoice number, and associated SOA
* Ops generates ZIPs from scan results; each ZIP contains all invoices for a head office plus the head office's SOA
* Ops sends emails in Active mode (real send) or Test/Dry-run mode (no emails sent, full log preview)
* Internal reporters receive a summary email after the send run completes
* Ops can authenticate via SMTP (including Gmail app passwords) or Microsoft 365 via OAuth device code flow (Microsoft Graph API)

# Functional Requirements

## Settings

* All settings are persisted across sessions in an encrypted config file (`config.enc`)
* Settings include:
  * Invoice folder path
  * SOA folder path
  * Customer list file path (`.xlsx`)
  * ZIP output folder path (blank = same directory as the database)
  * Aggregate by: `head_office` (default) or `customer_number`
  * Mode: `Active` (sends real emails) or `Test` (dry run, no emails sent)
  * Email auth method: `smtp` or `ms_auth`
* SMTP settings: host, port, username, password, from address, STARTTLS toggle
* Microsoft Auth settings: sender email address, authority (`organizations` for work/school, `consumers` for personal Microsoft accounts)
* Email template settings: subject template, body template (supporting variables `{head_office_name}`, `{contact_name}`, `{sender_name}`, `{month_year}`, `{period}`, `{month}`, `{year}`), sender display name, reporter email addresses (comma-separated)
* Billing month and year default to the previous calendar month on each app launch to prevent accidental wrong-period sends

## Scan

* On each scan, the database is fully rebuilt from source files (no incremental update)
* Customer list Excel is parsed row by row; each row yields a customer record linked to a head office
* Invoice PDFs are discovered recursively (case-insensitive glob `*invoice*.pdf`) and parsed by filename regex to extract customer number, invoice number, and ship name
* Invoice date is extracted from a bounding-box region of the PDF (upper-left quadrant); OCR fallback is supported via Tesseract if direct text extraction fails
* SOA PDFs are discovered recursively (case-insensitive glob `Statement*.pdf`) and parsed by filename regex to extract head office code and head office name
* SOA date is extracted from a bounding-box region of the PDF (upper-right area)
* Invoices are matched to customers and SOAs are matched to head offices via the parsed codes
* Scan retrieves invoices for the selected billing month **and the following month** to handle cross-month invoice dates
* Scan results are displayed per invoice with: customer aggregate key, head office name, customer number, ship name, invoice number, invoice date, invoice filename, and SOA filename

## Zip

* One ZIP file is produced per head office (or per customer number, depending on aggregate setting)
* Each ZIP contains: all matched invoice PDFs for that head office + the head office's SOA PDF
* ZIP files are named `{HeadOfficeCode}.zip` and stored in the configured output folder
* Files inside the ZIP use their original basenames (no folder structure preserved)
* ZIP compression: DEFLATE

## Send

* Emails are sent one per head office (aggregate group)
* Each email attaches the corresponding ZIP file
* Recipients are the union of all `emailforinvoice` addresses for all customers in that head office; duplicates are removed and recipients are sorted alphabetically
* Subject and body are rendered from user-configured templates
* Active mode: emails are sent via SMTP or Microsoft Graph API
* Test mode: no network calls are made; a full log of what would be sent (recipients, subject, body) is returned for review
* After all client emails are sent, a summary report email is sent to the configured reporter addresses
* SMTP: single connection reused for all emails; supports optional STARTTLS and optional username/password auth (supports unauthenticated relay)
* Microsoft Auth: device code flow via MSAL; token is cached encrypted in `config.enc` and reused silently on subsequent runs; sending via Microsoft Graph API (`POST /me/sendMail`)

## Database

* SQLite database, rebuilt on every Scan/Zip/Send action
* Tables: `clients` (customer number, head office, email addresses), `invoices` (invoice number, customer, ship name, file path, date, period, sent status), `soa` (head office, name, file path, date, period, sent status)
* Sent-status tracking columns exist in schema (for future use); emails are re-sent on each run regardless

# Non-Functional Requirements

## Security

* Config file is encrypted at rest using Fernet symmetric encryption
* Encryption key stored in OS keyring (preferred), Windows DPAPI-protected key file (fallback on Windows), or plain key file (last resort)
* MSAL token cache is stored inside the encrypted config; no plaintext token files are written
* SMTP passwords and MS credentials never appear in plain text on disk

## Platform

* Packaged as a single-file Windows executable via PyInstaller (`--onefile --noconsole`)
* Data and config stored in `%LOCALAPPDATA%\InvoiceMailer\` on Windows, `~/.invoicemailer/` elsewhere
* Dev mode uses local working directory paths and a local SQLite file

## Performance / Reliability

* All long-running operations (scan, zip, send) execute in background daemon threads; the GUI remains responsive
* OCR fallback for PDF text extraction is enabled by default but degrades gracefully if Tesseract is not installed
* SMTP connection is established once and reused across all emails in a send run
* Microsoft Graph token is acquired silently from cache when possible; interactive device code flow is triggered only when the cache is empty or expired

## Usability

* GUI is Tkinter-based, 1000×800 window, organised into tabs: Settings, Email Settings, Scan, Zip, Send & Logs
* Send tab displays a live scrolling log and a progress indicator
* Mode banner on Send tab clearly indicates Active vs Test mode and updates dynamically
* Settings are summarised in a read-only panel on the Settings tab; passwords are masked
* Microsoft token status (valid/empty/expired) is displayed in the Settings tab
