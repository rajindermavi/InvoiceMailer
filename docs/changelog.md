# Changelog

## 2026-04-08

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

### Dead code removal (L1)

`workflow.py` had an unreachable `if email_report is None` guard — `send_all_emails` is typed and always returns a `str`. Removed the dead branch.
