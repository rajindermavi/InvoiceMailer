from __future__ import annotations

import src.backend.utility.send as email_util


def test_normalize_recipients_splits_semicolon_recipients():
    recipients = email_util.normalize_recipients([
        "alice@example.com; bob@example.com",
    ])

    assert recipients == ["alice@example.com", "bob@example.com"]


def test_normalize_recipients_dedupes_and_strips_recipients():
    recipients = email_util.normalize_recipients([
        " alice@example.com; bob@example.com ; alice@example.com ",
        "bob@example.com",
    ])

    assert recipients == ["alice@example.com", "bob@example.com"]


def test_normalize_recipients_skips_invalid_addresses(caplog):
    caplog.set_level("WARNING")
    recipients = email_util.normalize_recipients([
        "valid@example.com; invalid-email; another@example.com",
    ])

    assert recipients == ["valid@example.com", "another@example.com"]
    assert "Skipping invalid email address" in caplog.text
