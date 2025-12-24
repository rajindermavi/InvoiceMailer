from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Mapping

from backend.config import SecureConfig

DEFAULT_SUBJECT_TEMPLATE = "Invoice Statement for {month}-{year}"
DEFAULT_BODY_TEMPLATE = (
    "Dear {contact_name},\n\n"
    "Please find attached the invoice statement for {month}-{year}.\n\n"
    "Best regards,\n"
    "{sender_name}"
)
DEFAULT_SENDER_NAME = "Billing Department"
REPORTER_EMAILS_PLACEHOLDER = []
DEFAULT_PERIOD_MONTH = datetime.now().month - 1 or 12
DEFAULT_PERIOD_YEAR = datetime.now().year if DEFAULT_PERIOD_MONTH != 12 else datetime.now().year - 1

# Default values used when no encrypted config is present.
DEFAULT_SETTINGS: Dict[str, Any] = {
    "invoice_folder": "",
    "soa_folder": "",
    "output_folder": "",
    "client_file": "",
    "aggregate_by": "head_office",
    "mode": "Active",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": "587",
    "ms_smtp_host":"smtp.office365.com",
    "ms_smtp_port":"587",
    "ms_username":"",
    "ms_token_cache":"",
    "ms_token_ts":"",
    "smtp_username": "",
    "smtp_password": "",
    "smtp_from": "",
    "smtp_use_tls": True,
    "email_auth_method": "smtp",
    "subject_template": DEFAULT_SUBJECT_TEMPLATE,
    "body_template": DEFAULT_BODY_TEMPLATE,
    "sender_name": DEFAULT_SENDER_NAME,
    "reporter_emails": REPORTER_EMAILS_PLACEHOLDER,
    "email_month": DEFAULT_PERIOD_MONTH,
    "email_year": DEFAULT_PERIOD_YEAR,
}


def load_settings(secure_config: SecureConfig) -> Dict[str, Any]:
    """
    Load config from SecureConfig with defaults filled in.
    """
    data = secure_config.load()
    merged = DEFAULT_SETTINGS.copy()
    for key, value in (data or {}).items():
        if key in merged:
            merged[key] = value
    # Guard against persisted empty strings for email templates.
    merged["subject_template"] = merged.get("subject_template") or DEFAULT_SUBJECT_TEMPLATE
    merged["body_template"] = merged.get("body_template") or DEFAULT_BODY_TEMPLATE
    return merged


def persist_settings(secure_config: SecureConfig, settings: Mapping[str, Any]) -> None:
    """
    Persist the settings dict via SecureConfig.
    Merge into existing secure config so MSAL token cache and other extras survive.
    """
    existing = secure_config.load() or {}
    merged = dict(existing)
    # Avoid overwriting the MSAL token cache (managed by MSalDeviceCodeTokenProvider)
    filtered_settings = {
        key: value for key, value in dict(settings).items()
        if key != "ms_token_cache"
    }
    merged.update(filtered_settings)
    secure_config.save(merged)


def apply_settings_to_vars(vars_map: Mapping[str, Any], settings: Mapping[str, Any]) -> None:
    """
    Set Tkinter Variable instances from a settings dict.
    """
    for key, var in vars_map.items():
        var.set(settings.get(key, DEFAULT_SETTINGS.get(key, "")))

def reset_month_and_year():
    RESET_MONTH_AND_YEAR = {
        "email_month": DEFAULT_PERIOD_MONTH,
        "email_year": DEFAULT_PERIOD_YEAR,
    }
    return RESET_MONTH_AND_YEAR

def settings_from_vars(vars_map: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Read values from Tkinter Variable instances into a settings dict.
    """
    settings: Dict[str, Any] = {}
    for key, var in vars_map.items():
        value = var.get()
        if isinstance(value, str):
            value = value.strip()
        settings[key] = value
    return settings
