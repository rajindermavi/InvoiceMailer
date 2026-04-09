# Invoice Mailer — Code Audit Report
**Date:** 2026-04-08  
**Scope:** Full codebase review — security, logic correctness, silent failures, code quality  
**Auditor:** Claude (claude-sonnet-4-6)

---

## Summary

The codebase is well-structured and shows deliberate attention to security (encryption at rest, parameterized SQL, background threading). However, several issues were found that range from runtime crashes under reachable conditions to business-logic gaps that can cause invoices to be silently missed. Four findings are rated **Critical/High** because they either crash the application or silently produce wrong business outcomes.

---

## Severity Legend

| Level    | Meaning |
|----------|---------|
| Critical | Will crash or lose data on reachable input |
| High     | Incorrect business outcome; user may not notice |
| Medium   | Potential crash or security concern under specific conditions |
| Low      | Code quality, edge case, or defensive gap |

---

## Findings

---

### F-01 · `get_client_list` — `UnboundLocalError` on any non-canonical input ✅ Fixed
**File:** [src/backend/db/db.py:292-306](src/backend/db/db.py#L292-L306)  
**Severity:** Critical

```python
def get_client_list(client_type: Optional[str] = None) -> list[str]:
    if client_type == 'head_office':
        query = "SELECT distinct head_office FROM clients WHERE 1=1"
        client_type = 'head_office'
    
    if client_type == 'customer_number':
        query = "SELECT distinct customer_number FROM clients WHERE 1=1"
        client_type = 'customer_number'

    with get_conn() as conn:
        cur = conn.execute(query)   # ← UnboundLocalError if neither branch ran
```

`query` is only assigned inside the two `if` branches. If `client_type` is `None`, any other string, or even if called with no argument, `query` is never assigned and the `conn.execute(query)` line raises `UnboundLocalError: local variable 'query' referenced before assignment`. The function has no default branch and no guard. This crashes every workflow action (Scan, Zip, Send) because all three call `get_client_list`.

**Fix:** Add an `else` branch that raises `ValueError` with a descriptive message, or assign a default query for `None`.

---

### F-02 · `emailforinvoice1 NOT NULL` constraint violated for clients with no email ✅ Fixed
**File:** [src/backend/db/db.py:88](src/backend/db/db.py#L88), [src/backend/db/db.py:154-156](src/backend/db/db.py#L154-L156)  
**Severity:** Critical

The schema declares:
```sql
emailforinvoice1  TEXT  NOT NULL
```

But `add_or_update_client` pads the email list with `None`:
```python
email_list = [email for email in emails if email][:5]
if len(email_list) < 5:
    email_list.extend([None] * (5 - len(email_list)))
```

If the client list Excel has a row with zero email addresses, `email_list[0]` is `None`, which violates the `NOT NULL` constraint. SQLite will raise `sqlite3.IntegrityError`, crashing `db_mgmt` and aborting the entire DB rebuild. Every client after that one in the file will also be missing.

**Fix:** Either make `emailforinvoice1` nullable in the schema (consistent with columns 2–5), or log a warning and skip rows with no email address in `db_utility.py`.

---

### F-03 · `prep_invoice_zips` fetches emails by wrong key when `agg='customer_number'` ✅ Fixed
**File:** [src/backend/workflow.py:69-90](src/backend/workflow.py#L69-L90)  
**Severity:** High

```python
for head_office, invoices in invoices_to_ship.items():
    ...
    email_list = get_client_email(head_office=head_office)
```

The loop variable is named `head_office` but `invoices_to_ship` is keyed by whatever `agg` is — either `'head_office'` or `'customer_number'`. When `agg='customer_number'`, the dict is keyed by customer numbers, so `head_office` here actually holds a customer number. `get_client_email(head_office=<customer_number>)` will find no row and return `[]`. Every batch will have an empty email list and no emails will be sent. The send step will complete without error, giving the impression that work was done.

**Fix:** Thread the `agg` parameter into `prep_invoice_zips` and call `get_client_email(**{agg: key})` rather than hardcoding `head_office=`.

---

### F-04 · Reporter summary email has no exception handling — activity log is lost on failure ✅ Fixed
**File:** [src/backend/utility/send.py:265-275](src/backend/utility/send.py#L265-L275), [src/backend/utility/send.py:326-333](src/backend/utility/send.py#L326-L333)  
**Severity:** High

Both the MS Graph and SMTP paths send a summary report at the end:
```python
# _send_via_graph
if reporter_emails and activity:
    ...
    client.send(**report_kwargs)   # ← no try/except

# _send_via_smtp
if reporter_emails and activity:
    ...
    server.send_message(report)   # ← no try/except
```

If the reporter email fails (bad address, server disconnect, quota exceeded), the exception propagates out of `send_all_emails`. In `_send_thread` in [send_gui.py:117-120](src/gui/notebook/send_gui.py#L117-L120), `_on_send_error` is called and the activity log is logged to the text box, but the GUI signals failure. More critically, in the SMTP case the server connection context-manager has already closed (the exception was raised inside the `with smtplib.SMTP(...)` block), so the activity log built up during client sends is still in `activity`, but `_build_log` is never called and the caller never gets the log string — it is silently lost.

**Fix:** Wrap the reporter email send in a `try/except` that logs the failure without propagating.

---

### F-05 · `str.format(**fmt)` on user-controlled templates — KeyError crashes entire send ✅ Fixed
**File:** [src/backend/utility/send.py:88](src/backend/utility/send.py#L88)  
**Severity:** Medium

```python
return subject_template.format(**fmt), body_template.format(**fmt)
```

If a user puts an unknown placeholder in their template (e.g., `{company_name}`, `{invoice_count}`), Python raises `KeyError`. This exception is not caught in `_render_templates`. It bubbles up through `build_email` → the per-batch `try/except` in `_send_via_smtp`, so each batch logs "FAILED" with a confusing `KeyError: 'company_name'` message. In dry-run mode there is no `try/except`, so the KeyError propagates all the way to the GUI error dialog, and no preview is shown at all.

Additionally, Python's `str.format()` on a user-controlled template string allows attribute access via dotted notation (e.g., `{sender_name.__class__.__mro__}`). While all `fmt` values are strings and the practical exploitation surface is limited, this pattern is worth replacing with a safer renderer.

**Fix:** Wrap the `.format()` calls in a `try/except KeyError` and produce a clear message naming the unknown key. Consider switching to a `string.Template` with `safe_substitute()` which is immune to attribute-access abuse and produces no error on unknown keys.

---

### F-06 · Invoices and SOAs silently skipped when date extraction fails ✅ Fixed
**File:** [src/backend/db/db_utility.py:50-53](src/backend/db/db_utility.py#L50-L53), [src/backend/db/db_utility.py:72-75](src/backend/db/db_utility.py#L72-L75)  
**Severity:** High (business logic)

```python
invoice_date = extract_pdf_date(inv_file_path, field='inv_date')
if invoice_date is None:
    logger.warning("Could not extract invoice date from %s — skipping", file.name)
    continue
```

If PDF date extraction fails — due to a different PDF layout, missing Tesseract, a scanned image-only PDF — the invoice is silently dropped from the database. It will not appear in Scan, will not be zipped, and will not be sent. The only notification is a `logger.warning()` which goes to the Python logging system. In the production EXE, no logging handler is configured, so this warning is swallowed entirely. The user sees a normal Scan result with no indication that any invoice was omitted.

The same applies to SOA files.

**Fix:** Collect all skipped files during `db_mgmt` and surface them to the GUI (e.g., return a list of warnings from `db_mgmt` and display them in the Scan tab after population).

---

### F-07 · `SecureConfig._log()` uses `print()` — lost in production EXE, exposes paths ✅ Fixed
**File:** [src/backend/config.py:117-119](src/backend/config.py#L117-L119), [src/backend/config.py:309](src/backend/config.py#L309)  
**Severity:** Medium

`SecureConfig` uses `print(f"[SecureConfig] {message}")` for all diagnostics. In the production PyInstaller build (`--noconsole`), stdout is not connected and all output is silently dropped. This means:
- Encryption key storage location is never communicated to the user
- DPAPI failures are invisible
- The `"All data securely encrypted!"` confirmation (line 309) is also silently dropped

Additionally, the log messages include the full filesystem path (`Storage directory: C:\Users\<username>\AppData\Local\InvoiceMailer\`) at INFO-equivalent priority. This is not sensitive in isolation but leaks the username in environments where logs are forwarded.

**Fix:** Replace `print()` with `logging.getLogger(__name__)`. Move path messages to `DEBUG` level. Surface key security events (DPAPI fail, keyring fallback) through the GUI.

---

### F-08 · Fernet key written in plaintext on non-Windows when keyring unavailable ✅ Fixed
**File:** [src/backend/config.py:215-218](src/backend/config.py#L215-L218)  
**Severity:** Medium (security)

```python
self._log(f"Writing key file: {key_file}")
key_file.write_bytes(key)   # ← plaintext Fernet key on disk
```

The last-resort fallback writes the raw Fernet key to `~/.invoicemailer/encryption.key` without any protection. Anyone with read access to the home directory can decrypt `config.enc` and retrieve SMTP passwords or other credentials. The user is not warned that their config is insecurely stored.

On Windows, the fallback correctly uses DPAPI (`CryptProtectData`) and raises `RuntimeError` if that also fails. The non-Windows path silently proceeds.

**Fix:** At minimum, log a clearly visible warning (ideally a GUI dialog) that the config is protected only by filesystem permissions. Consider refusing to save credentials in this state, or offering to encrypt with a user passphrase.

---

### F-09 · `DB_PATH` resolved at module import time — testing and runtime hazard
**File:** [src/backend/db/db.py:47](src/backend/db/db.py#L47)  
**Severity:** Low

```python
DB_PATH: Path = get_db_path()
```

`get_db_path()` is called once when `db.py` is first imported. If `APP_DB_PATH` is set or changed after the module is imported (e.g., in a test that reconfigures the environment between test cases), the module-level `DB_PATH` does not update. `_connect()` uses this cached value, so the change has no effect.

In tests, `APP_DB_PATH` must be set in the environment before the first import of `db`. If test isolation requires different paths per test, this module-level binding makes it impossible without reimporting.

**Fix:** Move `DB_PATH` resolution into `_connect()` (call `get_db_path()` at connection time) or use a module-level function rather than a constant.

---

### F-10 · `agg` parameter not validated — silent wrong behavior or opaque `TypeError`
**File:** [src/backend/workflow.py:34-36](src/backend/workflow.py#L34-L36)  
**Severity:** Low

```python
kwargs = {agg: client}
client_rows = get_client(**kwargs)
```

If `agg` is any string other than `'head_office'` or `'customer_number'`, `get_client()` receives an unexpected keyword argument and raises `TypeError: get_client() got an unexpected keyword argument '...'`. The caller gets a confusing message rather than a clear validation error.

**Fix:** Validate `agg` at the top of `scan_for_invoices` and raise `ValueError("agg must be 'head_office' or 'customer_number'")`.

---

### F-11 · No email address format validation before send
**File:** [src/backend/utility/send.py:48-58](src/backend/utility/send.py#L48-L58)  
**Severity:** Low

`normalize_recipients` deduplicates and strips addresses but does not check whether they are valid RFC 5321 email addresses. A malformed entry from the Excel file (extra spaces around `@`, missing domain, etc.) causes the SMTP server to reject the entire message for that batch. The per-batch exception handler catches this, but the error message is an SMTP server error code which is difficult for a non-technical user to interpret.

**Fix:** Add a basic regex or `email.headerregistry` validation in `normalize_recipients` and log a named warning per rejected address.

---

### F-12 · ZIP files silently overwritten on re-run
**File:** [src/backend/workflow.py:88](src/backend/workflow.py#L88)  
**Severity:** Low

```python
zip_path = collect_files_to_zip(files_to_zip_paths, base_zip_dir / f"{head_office}.zip")
```

`zipfile.ZipFile` in write mode (`"w"`) truncates an existing file. If the user runs Zip twice (e.g., to fix a settings error), the previous ZIP is replaced without warning. If the first ZIP had already been manually inspected, the user would be working with a different file. This also means any collision between two clients whose `head_office` codes normalize to the same filename results in one silently overwriting the other.

---

### F-13 · `dateutil.parser` with `fuzzy=True` may parse wrong dates from surrounding text
**File:** [src/backend/utility/extract_pdf_text.py:144](src/backend/utility/extract_pdf_text.py#L144)  
**Severity:** Low

```python
dt = dateparser.parse(d, dayfirst=True, fuzzy=True)
```

`fuzzy=True` instructs dateutil to try to extract a date from text that contains extra words. When applied to the regex-pre-filtered `d` strings this is mostly harmless, but the PDF region extraction sometimes includes surrounding text (especially in the `expanded` and `ocr_txt` passes). A line like `"Terms: Net 30 Days"` could be misinterpreted with `fuzzy=True` (e.g., the "30" could be parsed in combination with other text). An incorrect invoice date leads to an incorrect `inv_period_month`, causing the invoice to be placed in the wrong billing period and not appear in the Scan results for the correct month.

**Fix:** Since the regex patterns in `DATE_PATTERNS` already narrow the candidates to date-shaped strings, `fuzzy=False` is safer here. The regex filter is the right place to be permissive; `dateparser.parse` should be strict.

---

### F-14 · DB fully deleted and rebuilt on every workflow action — `sent` tracking is inert
**File:** [src/backend/db/db_utility.py:28-30](src/backend/db/db_utility.py#L28-L30)  
**Severity:** Low (design note)

```python
if db_path.exists():
    db_path.unlink()
init_db()
```

The database is dropped and recreated on every Scan, Zip, and Send action. The `sent`, `sent_at`, and `send_error` columns exist in the schema and `mark_invoice_sent` is implemented, but are never populated during a workflow run, and would be lost on the next rebuild even if they were. The schema implies a future audit-log capability that is currently inert.

This also means:
- If DB deletion succeeds but `init_db()` raises (e.g., disk full), the app has no database and subsequent reads fail with "no such table".
- Any partial state from a failed mid-run cannot be recovered.

**Fix (if audit trail is desired):** Move to an incremental upsert strategy (already partly implemented via `INSERT OR IGNORE` / `ON CONFLICT`) so the DB is not rebuilt from scratch. If the full-rebuild strategy is intentional, document it and remove the dead `sent`/`sent_at`/`send_error` columns.

---

## Positive Notes

These areas are handled well and should be preserved:

- **Parameterized SQL everywhere** — no concatenated query strings; SQL injection is not possible.
- **Fernet + OS keyring + DPAPI tiering** — thoughtful defense-in-depth for secrets at rest.
- **MSAL token cache preserved across saves** — the `ms_token_cache` exclusion in `persist_settings` prevents inadvertent token loss.
- **Per-batch exception handling in send loops** — one bad address does not stop all remaining sends.
- **Background threading** — all long operations run in daemon threads; the GUI never freezes.
- **STARTTLS negotiation check** — the explicit `has_extn("starttls")` guard prevents silent downgrade to plaintext SMTP.
- **`EmailMessage` API** — email headers are set via structured API, not string concatenation; header injection is not possible.

---

## Prioritized Fix Order

| Priority | Finding | Status | Reason |
|----------|---------|--------|--------|
| 1 | F-01 (`get_client_list` UnboundLocalError) | ✅ Fixed | Crashes every workflow on any non-standard `agg` input |
| 2 | F-02 (NOT NULL email constraint) | ✅ Fixed | Crashes DB rebuild for clients with no email |
| 3 | F-03 (wrong email lookup key in `agg=customer_number`) | ✅ Fixed | Silent wrong business outcome |
| 4 | F-04 (reporter email no error handling) | ✅ Fixed | Activity log silently lost on send errors |
| 5 | F-06 (invoices silently skipped on date failure) | ✅ Fixed | Invoices missed with no user feedback |
| 6 | F-05 (template KeyError crashes send) | ✅ Fixed | Confusing failure with user-visible impact |
| 7 | F-07 (`print()` in SecureConfig) | ✅ Fixed | Diagnostic info lost in production |
| 9 | F-09 (module-level DB_PATH) | Open | Testing reliability |
| 10 | F-10–F-14 | Open | Low-severity quality items |
