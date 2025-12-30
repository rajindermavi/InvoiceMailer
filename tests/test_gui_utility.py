from __future__ import annotations

import gui.utility as gui_util


class DummySecureConfig:
    def __init__(self, initial=None):
        self.initial = initial or {}
        self.saved = None

    def load(self):
        return self.initial

    def save(self, data):
        self.saved = data
        self.initial = data


class DummyVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


def test_load_settings_merges_defaults_and_templates():
    secure = DummySecureConfig(
        {
            "smtp_host": "smtp.example.com",
            "subject_template": "",
        }
    )

    settings = gui_util.load_settings(secure)

    assert settings["smtp_host"] == "smtp.example.com"
    assert settings["subject_template"] == gui_util.DEFAULT_SUBJECT_TEMPLATE
    assert settings["body_template"] == gui_util.DEFAULT_BODY_TEMPLATE


def test_persist_settings_preserves_token_cache():
    secure = DummySecureConfig({"ms_token_cache": "keep", "mode": "Active"})
    settings = {"mode": "Test", "ms_token_cache": "replace", "smtp_host": "smtp.local"}

    gui_util.persist_settings(secure, settings)

    assert secure.saved["ms_token_cache"] == "keep"
    assert secure.saved["mode"] == "Test"
    assert secure.saved["smtp_host"] == "smtp.local"


def test_apply_and_read_settings_from_vars():
    vars_map = {"smtp_host": DummyVar(), "mode": DummyVar()}
    settings = {"smtp_host": " smtp.example.com ", "mode": "Active"}

    gui_util.apply_settings_to_vars(vars_map, settings)
    assert vars_map["smtp_host"].get().strip() == "smtp.example.com"
    assert vars_map["mode"].get() == "Active"

    collected = gui_util.settings_from_vars(vars_map)
    assert collected["smtp_host"] == "smtp.example.com"
    assert collected["mode"] == "Active"


def test_reset_month_and_year_matches_defaults():
    result = gui_util.reset_month_and_year()
    assert result["email_month"] == gui_util.DEFAULT_PERIOD_MONTH
    assert result["email_year"] == gui_util.DEFAULT_PERIOD_YEAR
