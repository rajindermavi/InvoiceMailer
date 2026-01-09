from __future__ import annotations

from email.utils import getaddresses

import backend.utility.email as email_util


def _make_batch(tmp_path, email_list):
    zip_path = tmp_path / "invoices.zip"
    zip_path.write_bytes(b"zip")
    return email_util.ClientBatch(
        zip_path=zip_path,
        email_list=email_list,
        head_office_name="ACME Corp",
    )


def test_build_email_normalizes_semicolon_recipients(tmp_path):
    batch = _make_batch(tmp_path, ["alice@example.com; bob@example.com"])

    msg = email_util.build_email(
        batch,
        "from@example.com",
        email_util.DEFAULT_SUBJECT_TEMPLATE,
        email_util.DEFAULT_BODY_TEMPLATE,
        "Sender",
        "2024-05",
    )

    assert msg["To"] == "alice@example.com, bob@example.com"
    assert [addr for _, addr in getaddresses([msg["To"]])] == [
        "alice@example.com",
        "bob@example.com",
    ]


def test_build_email_dedupes_and_strips_recipients(tmp_path):
    batch = _make_batch(
        tmp_path,
        [" alice@example.com; bob@example.com ; alice@example.com ", "bob@example.com"],
    )

    msg = email_util.build_email(
        batch,
        "from@example.com",
        email_util.DEFAULT_SUBJECT_TEMPLATE,
        email_util.DEFAULT_BODY_TEMPLATE,
        "Sender",
        "2024-05",
    )

    assert msg["To"] == "alice@example.com, bob@example.com"
    assert [addr for _, addr in getaddresses([msg["To"]])] == [
        "alice@example.com",
        "bob@example.com",
    ]
