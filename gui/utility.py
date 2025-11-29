from __future__ import annotations

from typing import Any, Dict, Mapping

from backend.config import SecureConfig

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
    "smtp_username": "",
    "smtp_password": "",
    "smtp_from": "",
    "smtp_use_tls": True,
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
    return merged


def persist_settings(secure_config: SecureConfig, settings: Mapping[str, Any]) -> None:
    """
    Persist the settings dict via SecureConfig.
    """
    secure_config.save(dict(settings))


def apply_settings_to_vars(vars_map: Mapping[str, Any], settings: Mapping[str, Any]) -> None:
    """
    Set Tkinter Variable instances from a settings dict.
    """
    for key, var in vars_map.items():
        var.set(settings.get(key, DEFAULT_SETTINGS.get(key, "")))


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
