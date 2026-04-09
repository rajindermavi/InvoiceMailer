# Changelog

## 2026-04-08

### Insecure key-write confirmation dialog (F-08)

Addressed the F-08 audit finding in `docs/code_audit.md`.

- **`src/backend/config.py` · `SecureConfig.__init__`**: Added optional `confirm_insecure_write: Callable[[], bool] | None` parameter. When provided, this callback is invoked before the last-resort plaintext key write (non-Windows, no keyring). If the callback returns `False`, a `RuntimeError` is raised and the key is never written, preventing silent storage of credentials with no protection beyond filesystem permissions.

- **`src/gui/app_gui.py` · `InvoiceMailerGUI.__init__`**: Passes `_confirm_insecure_key_write` as the callback when constructing `SecureConfig`. The callback shows a `tkinter.messagebox.askokcancel` warning dialog explaining that the encryption key will be stored as a plain file. The user must click **OK** to proceed or **Cancel** to abort saving.

The backend layer remains GUI-free; the confirmation mechanism is injected as a callable at construction time, keeping the architecture boundary (GUI → Backend) intact.

---



### Removed `src/backend/utility/email.py`

Reviewed the boundary violations documented in `docs/system_contracts.md`:

- Violation 1: `src/backend/utility/email.py` imported `send_email_via_graph` from `src/gui/msal_device_code.py` (backend importing from GUI layer).
- Violation 2: `src/gui/msal_device_code.py` mixed `smtplib`, `msal`, and `requests` logic with `tkinter`.

**Finding:** Both violations were already resolved by the introduction of `src/backend/utility/send.py`, which handles all email dispatch (SMTP and MS Graph via `nicemail`) with no cross-layer imports. `src/gui/msal_device_code.py` no longer exists. `src/backend/workflow.py` had already been updated to import from `send.py`.

**Action:** Deleted the now-dead `src/backend/utility/email.py`. Its import of `src.gui.msal_device_code` was broken, and all its functionality had been superseded by `send.py`. No other module referenced it.

#### Summary of resolved boundary violations

| # | Violation | Fix |
|---|---|---|
| 1 | `src/backend/utility/email.py` imports `send_email_via_graph` from `src/gui/msal_device_code.py` | Move Graph/SMTP send helpers and `MSalDeviceCodeTokenProvider` to `src/backend/delivery/`; keep only the Tkinter popup in `src/gui/` |
| 2 | `src/gui/msal_device_code.py` contains `smtplib`, `msal`, `requests` logic mixed with `tkinter` | Split into `src/backend/delivery/ms_auth.py` (auth + send) and a thin GUI popup in `src/gui/` |

Once resolved, the only direction of cross-layer imports is downward:
GUI → Workflow → DB / Delivery / Utilities → Config.

### Silent failure hardening (H1–H7, M1, M3–M5)

Addressed all HIGH and most MEDIUM issues from `docs/silent_failure_audit.md`.
Two patterns applied:

**Fail fast with a clear error** (data loading phase):
- `db/db.py`: `get_client_email` now returns `[]` instead of crashing when `fetchone()` returns `None`.
- `db/db_utility.py`: `None` date from `extract_pdf_date()` now logs a warning and skips the file rather than raising `AttributeError`. Removed the useless outer `try/except Exception: raise` wrapper; replaced with per-item skip-and-warn.
- `backend/workflow.py`: empty `client_rows` now raises `ValueError` naming the missing client instead of an opaque `IndexError`.

**Collect-and-continue** (send loop):
- `utility/send.py`: Both the MS Graph and SMTP send loops now catch per-batch exceptions, write a `FAILED` entry to the activity log, and continue with remaining batches. Period parse failure now logs a `WARNING` instead of silently blanking `{month}`/`{year}` in templates.

**Logging for silent fallbacks**:
- `utility/extract_pdf_text.py`: OCR library import failure now logs which package is missing. Tesseract runtime failure logs the error rather than returning `""` silently.

### Config credential failure logging (M2)

Four silent `except Exception` paths in `SecureConfig` now call `self._log()` with the
exception detail, consistent with the existing logging style in that class:

- `_init_dpapi`: logs when `win32crypt` import fails on Windows.
- `_dpapi_decrypt` / `_dpapi_encrypt`: log when DPAPI operation fails before disabling DPAPI.
- `load()`: logs when JSON parse fails after DPAPI decrypt, and when Fernet decryption fails
  (corrupt file or key change). Fallback to `{}` is preserved in both cases.

### SMTP port validation (L3)

`app_gui.py` now calls `_parse_smtp_port()` instead of a bare `int()` conversion.
Non-numeric input raises `ValueError: SMTP port must be a number, got: <value>` rather
than a generic `ValueError: invalid literal for int()`.

L2 (`collect_files_to_zip` unguarded) was assessed and closed — missing files are
already caught at the scan step with a user-facing popup.

### Code audit fixes (F-01, F-02, F-03, F-04, F-05, F-06, F-07)

Addressed four findings from `docs/code_audit.md`:

- **F-01** (`db/db.py` · `get_client_list`): Replaced two consecutive `if` branches with `if / elif / else`. Any `client_type` that is not `'head_office'` or `'customer_number'` now raises `ValueError` with a descriptive message instead of crashing with `UnboundLocalError`. Also removed the redundant `WHERE 1=1` clause and the no-op self-reassignments.

- **F-02** (`db/db.py` · `add_or_update_client`): Added an early-return guard before the INSERT. If the email list is empty after filtering, a `warnings.warn` is issued naming the client and the function returns without touching the DB, preventing a `sqlite3.IntegrityError` from the `emailforinvoice1 NOT NULL` constraint.

- **F-03** (`workflow.py` · `prep_invoice_zips`): Added `agg` parameter (default `"head_office"`). Renamed the loop variable from `head_office` to `client_key` throughout the function. Email lookup changed from `get_client_email(head_office=head_office)` to `get_client_email(**{agg: client_key})`, fixing silent empty-email-list when `agg='customer_number'`. Both GUI call sites (`send_gui.py`, `zip_gui.py`) updated to pass `agg=workflow_kwargs["agg"]`.

- **F-04** (`utility/send.py` · reporter summary): Wrapped the reporter summary `client.send()` call in `_send_via_graph` and the `server.send_message()` call in `_send_via_smtp` in `try/except`. A reporter failure now logs the error and returns normally, so the activity log is always returned to the caller.

- **F-05** (`utility/send.py` · template rendering): Replaced `str.format(**fmt)` with `string.Template.safe_substitute()`. Unknown placeholders are now left as-is instead of raising `KeyError`, and attribute-access abuse via `{obj.attr}` syntax is no longer possible. A `_BRACE_VAR` regex converts legacy `{key}` syntax to `${key}` at render time so existing stored configs continue to work without migration. Default templates in `send.py` and `gui/utility.py` updated to `${key}` syntax.

- **F-06** (`db/db_utility.py` · `db_mgmt`): `db_mgmt` now returns `list[str]` of warning messages for every file skipped (date extraction failure, SOA filename mismatch). All three GUI threads (`scan_gui`, `zip_gui`, `send_gui`) capture the returned list and surface it in the UI — the Scan tab shows skipped files under the results table, the Zip tab appends them to the status label, and the Send tab logs them to the activity text box before sending.

- **F-07** (`config.py` · `SecureConfig`): Replaced `print()` with `logging.getLogger(__name__)`. Routine operational messages use `logger.debug()`; security-degraded paths (DPAPI unavailable, keyring lookup/save failure, unprotected key file written) use `logger.warning()`. The standalone `print("All data securely encrypted!")` in `_announce_encryption_status` is now routed through `logger.debug()`. No diagnostic output goes to stdout.

### Dead code removal (L1)

`workflow.py` had an unreachable `if email_report is None` guard — `send_all_emails` is typed and always returns a `str`. Removed the dead branch.
