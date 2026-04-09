# System Contracts

Defines the public interface and boundary rules for each module in the codebase.
The goal is to regularize what is already in place — not to redesign it.

---

## Layer Map

```
┌─────────────────────────────────────────────────────┐
│  GUI  (src/gui/)                                    │
│  app_gui · notebook tabs · msal popup               │
│  gui/utility  (settings load/save, Tk var helpers)  │
└────────────────────┬────────────────────────────────┘
                     │ calls
┌────────────────────▼────────────────────────────────┐
│  Workflow  (src/backend/workflow.py)                 │
│  scan_for_invoices · prep_invoice_zips              │
│  prep_and_send_emails                               │
└──────┬───────────────────────────────┬──────────────┘
       │ calls                         │ calls
┌──────▼──────────┐         ┌──────────▼──────────────┐
│  DB             │         │  Utilities               │
│  src/backend/db │         │  extract · read_xlsx     │
│                 │         │  packaging · delivery    │
└──────┬──────────┘         └──────────┬──────────────┘
       │                               │
┌──────▼───────────────────────────────▼──────────────┐
│  Config  (src/backend/config.py)                    │
│  SecureConfig · paths · regex · pdf rect settings   │
└─────────────────────────────────────────────────────┘
```

**Layer rules:**
- Lower layers must not import from upper layers
- GUI may import from Workflow and below
- Workflow may import from DB, Utilities, and Config
- Utilities may import from Config only
- DB may import from Config (path only)
- Config has no internal imports

**Current violation to resolve:**
`src/backend/utility/email.py` imports `send_email_via_graph` from `src/gui/msal_device_code.py`.
This is a backend module importing from the GUI layer. The fix is tracked under the
[Delivery](#delivery-srcbackenddelivery) section below: Graph/SMTP sending moves to
`src/backend/delivery/`, and the GUI retains only the Tkinter device-code popup.

---

## Config — `src/backend/config.py`

**Purpose:** Application environment detection, encrypted settings storage, and static
configuration constants (regex patterns, PDF bounding-box coordinates).

**Public interface:**

| Name | Kind | Description |
|---|---|---|
| `SecureConfig` | class | Load/save JSON config encrypted with Fernet; key stored in OS keyring or DPAPI file |
| `SecureConfig.load() -> dict` | method | Decrypt and return config as plain dict |
| `SecureConfig.save(config_dict: dict)` | method | Encrypt and persist config dict |
| `SecureConfig.is_keyring_backed() -> bool` | method | Whether the Fernet key is in the OS keyring |
| `get_app_env() -> str` | function | `"development"` or `"production"` |
| `get_storage_dir() -> Path` | function | Platform-specific dir for config and key files |
| `get_encrypted_config_path() -> Path` | function | Path to `config.enc` |
| `get_date_regex() -> list[re.Pattern]` | function | Compiled date-matching patterns |
| `get_file_regex(type: str) -> re.Pattern` | function | Compiled invoice or SOA filename pattern |
| `pdf_rect_settings: dict` | constant | Percent-based bounding boxes for PDF field extraction |
| `page_index: int` | constant | PDF page to read (0 = first) |
| `try_ocr_if_needed: bool` | constant | Whether to fall back to Tesseract OCR |

**Allowed imports:** stdlib only (`os`, `sys`, `re`, `json`, `pathlib`), `cryptography.fernet`, `keyring`, `win32crypt` (optional Windows only).

**Forbidden imports:** Nothing from `src/backend/db`, `src/backend/utility`, `src/backend/workflow`, or `src/gui`.

---

## DB — `src/backend/db/`

### `db_path.py`
**Purpose:** Resolve the SQLite file path from environment and env-var override.

| Name | Kind | Description |
|---|---|---|
| `get_db_path() -> Path` | function | Canonical path to `invoice_mailer.sqlite3` |

**Allowed imports:** `src/backend/config` (env helpers only), stdlib.

### `db.py`
**Purpose:** All SQLite read and write operations. Single source of truth for data access.

**Write interface:**

| Function | Description |
|---|---|
| `init_db()` | Create tables and indexes if absent |
| `add_or_update_client(head_office, customer_number, emails)` | Upsert client row |
| `add_or_update_soa(head_office, head_office_name, soa_file_path, soa_date, soa_period_month)` | Upsert SOA row |
| `record_invoice(tax_invoice_no, customer_number, ship_name, inv_file_path, invoice_date, period_month)` | Insert invoice (ignore on conflict) |
| `mark_invoice_sent(file_path, sent_at, error)` | Update sent status (infrastructure, not yet called in send flow) |

**Read interface:**

| Function | Returns | Description |
|---|---|---|
| `get_client_list(client_type) -> list[str]` | distinct aggregate keys | `client_type`: `"head_office"` or `"customer_number"` |
| `get_client(head_office, customer_number) -> list[Row]` | client rows | At least one filter required |
| `get_invoices(head_office, customer_number, period_month, sent) -> list[Row]` | invoice rows | All filters optional |
| `get_client_email(head_office, customer_number) -> list[str]` | non-null email addresses | Returns all five slots that have a value |
| `get_soa_by_head_office(head_office, head_office_name, period_month, sent) -> list[Row]` | SOA rows | All filters optional |

**Allowed imports:** `src/backend/db/db_path`, stdlib (`sqlite3`, `contextlib`, `pathlib`, `warnings`).

**Forbidden imports:** `src/backend/utility`, `src/backend/workflow`, `src/gui`.

### `db_utility.py`
**Purpose:** DB lifecycle management. Owns the "rebuild from source files" operation
that runs at the start of every Scan/Zip/Send action.

| Function | Description |
|---|---|
| `db_mgmt(client_file, invoice_folder, soa_folder)` | Delete and recreate the SQLite DB; scan folders and populate all three tables |

Internally calls `init_db`, `add_or_update_client`, `record_invoice`, `add_or_update_soa`,
`iter_xlsx_rows_as_dicts`, `extract_pdf_date`, and `get_file_regex`.

**Allowed imports:** `src/backend/db/db`, `src/backend/db/db_path`, `src/backend/utility/read_xlsx`, `src/backend/utility/extract_pdf_text`, `src/backend/config`, stdlib.

**Forbidden imports:** `src/backend/workflow`, `src/gui`.

---

## Utilities — `src/backend/utility/`

### `extract_pdf_text.py`
**Purpose:** Extract raw text and dates from PDF bounding-box regions.

| Name | Kind | Description |
|---|---|---|
| `extract_pdf_text(pdf_path, field, page_index, padding) -> str` | function | Raw text from named bounding box; tries direct → expanded → OCR |
| `extract_pdf_date(pdf_path, field, page_index, padding) -> str \| None` | function | ISO date string from named bounding box, or `None` |
| `find_date_strings(text) -> list[str]` | function | All regex-matched date substrings from a text block |
| `normalize_first_date(dates) -> str \| None` | function | Parse and normalize the first parseable date to ISO format |

**Allowed imports:** `src/backend/config` (rect settings, regex, OCR flag), `fitz` (PyMuPDF), `dateutil`, `pytesseract`/`PIL` (optional), stdlib.

**Forbidden imports:** `src/backend/db`, `src/backend/workflow`, `src/gui`.

### `read_xlsx.py`
**Purpose:** Iterate rows of an Excel file as dicts.

| Name | Kind | Description |
|---|---|---|
| `iter_xlsx_rows_as_dicts(filepath, sheet_name, header_row) -> Iterator[dict]` | function | Yield one dict per data row; keys are header cell values |

**Allowed imports:** `openpyxl`, stdlib.

**Forbidden imports:** All `src/` modules.

### `packaging.py`
**Purpose:** Collect files into a ZIP archive.

| Name | Kind | Description |
|---|---|---|
| `collect_files_to_zip(file_paths, zip_path) -> Path` | function | Write all `file_paths` into `zip_path` (DEFLATE); returns the created Path |

Raises `FileNotFoundError` if any source file is missing.
Files are stored with basename only (`arcname=file.name`).

**Allowed imports:** stdlib (`zipfile`, `pathlib`).

**Forbidden imports:** All `src/` modules.

---

## Delivery — `src/backend/delivery/`

> **Migration target.** The email-sending and auth-token code currently split
> across `src/backend/utility/email.py` and `src/gui/msal_device_code.py`
> belongs here. Moving it eliminates the upward import from
> `src/backend/utility/email.py` → `src/gui/`.
>
> **Future:** When the `NiceMail` framework is adopted it will replace the
> current SMTP and Graph implementations inside this module. The public
> interface (`ClientBatch`, `send_all_emails`) should remain stable so that
> `workflow.py` does not need to change.

### Current files to consolidate here

| Current location | Moves to |
|---|---|
| `src/backend/utility/email.py` | `src/backend/delivery/email.py` |
| `src/gui/msal_device_code.py` — token provider + Graph/SMTP send helpers | `src/backend/delivery/ms_auth.py` |
| `src/gui/msal_device_code.py` — Tkinter device-code popup | stays in `src/gui/` |

### Public interface

**Data classes**

| Name | Fields | Description |
|---|---|---|
| `ClientBatch` | `zip_path: Path`, `email_list: list[str]`, `head_office_name: str` | One email shipment unit |
| `SMTPConfig` | `host, port, username, password, from_addr, use_tls` | SMTP connection parameters |
| `MSAuthConfig` | `host, port, starttls, ms_email_address` | MS OAuth SMTP parameters (used when not sending via Graph) |

**Functions**

| Function | Description |
|---|---|
| `normalize_recipients(email_list) -> list[str]` | Split semicolon-separated entries, strip whitespace, drop empties |
| `build_email(batch, from_addr, subject_template, body_template, sender_name, period) -> EmailMessage` | Render templates and attach ZIP |
| `send_all_emails(batches, email_auth_method, smtp_conf, ms_auth_conf, dry_run, subject_template, body_template, sender_name, period, reporter_emails, token_provider, secure_config) -> str` | Send all batches; return activity log string |

**Template variables available in subject and body:**
`{head_office_name}`, `{contact_name}` (alias), `{sender_name}`, `{month_year}`, `{period}`, `{month}`, `{year}`

**MS Auth helpers** (from `ms_auth.py`)

| Name | Kind | Description |
|---|---|---|
| `MSalDeviceCodeTokenProvider` | class | MSAL public-client token cache with silent + device-code acquisition |
| `MSalDeviceCodeTokenProvider.acquire_token(interactive, scopes) -> str` | method | Return a valid access token; raise `RuntimeError` if unavailable |
| `MSalDeviceCodeTokenProvider.set_authority(authority)` | method | Switch between `organizations` and `consumers` tenants |
| `GraphMailClient` | class | Context-manager wrapper for Graph `sendMail` HTTP POST |
| `GraphMailClient.send_message(msg: EmailMessage)` | method | POST email to Graph API |
| `connect_graph_with_oauth(cfg, token_provider, interactive, secure_config) -> GraphMailClient` | function | Acquire token and return ready `GraphMailClient` |
| `send_email_via_graph(cfg, msg, token_provider, interactive, secure_config)` | function | Convenience: connect, send one `EmailMessage`, close |
| `connect_smtp_with_oauth(cfg, token_provider, interactive, secure_config) -> smtplib.SMTP` | function | Acquire token and return authenticated SMTP connection (XOAUTH2) |
| `send_email_via_smtp_oauth(cfg, msg, token_provider, interactive, secure_config)` | function | Convenience: connect, send one `EmailMessage`, close |

`MSalDeviceCodeTokenProvider.__init__` accepts a `show_message` callback for
the device-code display step. The GUI injects its Tkinter popup via this callback;
no Tkinter import lives in the delivery layer.

**Allowed imports:** `src/backend/config`, stdlib (`smtplib`, `email`, `base64`), `msal`, `requests`, `cryptography`.

**Forbidden imports:** `src/gui`, `src/backend/db`, `src/backend/workflow`.

---

## Workflow — `src/backend/workflow.py`

**Purpose:** Orchestration. Combines DB, utilities, and delivery into the three
user-facing operations. No business logic of its own — sequences calls to lower layers.

| Function | Description |
|---|---|
| `scan_for_invoices(client_list, period_year, period_month, agg) -> dict[str, list[dict]]` | Match invoices and SOAs to clients for the selected period (and following month) |
| `prep_invoice_zips(invoices_to_ship, zip_output_dir) -> list[dict]` | ZIP invoices per aggregate group; return email shipment list |
| `prep_and_send_emails(email_auth_method, smtp_config, ms_auth_config, email_setup, email_shipment, period_str, dry_run, token_provider, secure_config) -> str` | Build `ClientBatch` list and call `send_all_emails`; return activity log |

**`invoices_to_ship` structure** (output of `scan_for_invoices`, input of `prep_invoice_zips`):
```python
{
    "<aggregate_key>": [
        {
            "head_office_name": str | None,
            "ship_name": str,
            "invoice_number": str,
            "invoice_date": str | None,
            "invoice_path": str,
            "soa_path": str | None,
            "customer_number": str,
        },
        ...
    ]
}
```

**`email_shipment` structure** (output of `prep_invoice_zips`, input of `prep_and_send_emails`):
```python
[
    {
        "zip_path": Path,
        "email_list": list[str],
        "head_office_name": str,
    },
    ...
]
```

**Allowed imports:** `src/backend/db`, `src/backend/utility`, `src/backend/delivery`, `src/backend/config`, stdlib.

**Forbidden imports:** `src/gui`.

---

## GUI Utility — `src/gui/utility.py`

**Purpose:** Settings defaults, load/save helpers, and Tkinter variable adapters.
No widgets are constructed here.

| Name | Kind | Description |
|---|---|---|
| `DEFAULT_SETTINGS: dict` | constant | All settings keys with default values |
| `load_settings(secure_config) -> dict` | function | Load from `SecureConfig`, fill missing keys from defaults |
| `persist_settings(secure_config, settings)` | function | Merge into existing config and save; never overwrites `ms_token_cache` |
| `apply_settings_to_vars(vars_map, settings)` | function | Push settings values into Tkinter `Variable` instances |
| `settings_from_vars(vars_map) -> dict` | function | Pull values from Tkinter `Variable` instances into a plain dict |
| `reset_month_and_year() -> dict` | function | Return default month/year (previous calendar month) for session reset |

**Allowed imports:** `src/backend/config` (`SecureConfig`), stdlib (`datetime`).

**Forbidden imports:** `src/backend/db`, `src/backend/workflow`, `src/backend/delivery`, `tkinter` (no widgets here).

---

## GUI — `src/gui/`

### `app_gui.py`
**Purpose:** Application entry point and root window. Composes all tab mixins,
initializes `SecureConfig` and `MSalDeviceCodeTokenProvider`, and starts the Tkinter
event loop.

Owns `_build_workflow_kwargs() -> dict`, the single method that assembles all
settings into the parameter dict consumed by `workflow.py` functions.

**Allowed imports:** All `src/` modules, `tkinter`.

### `msal_device_code.py` (GUI portion, post-migration)

After the delivery migration only the Tkinter device-code popup remains here.

| Name | Kind | Description |
|---|---|---|
| `DeviceCodePopup` (or equivalent) | class / function | `tk.Toplevel` showing verification URL, user code, and copy buttons |

This is injected into `MSalDeviceCodeTokenProvider` as the `show_message` callback.
It has no knowledge of token acquisition or email sending.

**Allowed imports:** `tkinter`, stdlib.

**Forbidden imports:** `src/backend/delivery`, `msal`, `smtplib`, `requests`.

### Notebook tabs (`src/gui/notebook/`)

Each tab is a mixin class. All tabs follow the same contract:

- **Reads** settings from `self` (populated by `app_gui`)
- **Calls** only workflow-layer functions or `db_mgmt`
- **Dispatches** UI updates to the main thread via `self.root.after(0, ...)`
- **Runs** long operations in daemon threads
- **Never** imports from `src/backend/utility` or `src/backend/delivery` directly

| Tab class | File | Calls into |
|---|---|---|
| `SettingsTab` | `settings_gui.py` | `gui/utility`, `SecureConfig`, `MSalDeviceCodeTokenProvider` (via `app_gui`) |
| `EmailSettingsTab` | `email_gui.py` | `gui/utility` |
| `ScanTab` | `scan_gui.py` | `db_utility.db_mgmt`, `db.get_client_list`, `workflow.scan_for_invoices` |
| `ZipTab` | `zip_gui.py` | `db_utility.db_mgmt`, `db.get_client_list`, `workflow.scan_for_invoices`, `workflow.prep_invoice_zips` |
| `SendTab` | `send_gui.py` | `db_utility.db_mgmt`, `db.get_client_list`, `workflow.scan_for_invoices`, `workflow.prep_invoice_zips`, `workflow.prep_and_send_emails` |

---

