from __future__ import annotations

import datetime as dt

import pytest

import backend.db.db as db_module


@pytest.fixture
def initialized_db(monkeypatch, tmp_path):
    """Point the DB module at a temporary SQLite file and create schema."""
    temp_path = tmp_path / "invoice_mailer.sqlite3"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(db_module, "DB_PATH", temp_path)
    db_module.init_db()
    return temp_path


def test_add_or_update_client_persists_email_list(initialized_db):
    db_module.add_or_update_client(
        head_office="ACME Corp",
        customer_number="ACME123",
        emails=["one@example.com", "two@example.com", None],
    )

    db_module.add_or_update_client(
        head_office="ACME Corp",
        customer_number="ACME123",
        emails=["updated@example.com"],
    )

    emails = db_module.get_client_email(
        head_office="ACME Corp", customer_number="ACME123"
    )
    assert emails == ["updated@example.com"]


def test_record_invoice_and_mark_sent(initialized_db):
    db_module.add_or_update_client(
        head_office="Beta Corp",
        customer_number="BETA456",
        emails=["ops@beta.test"],
    )

    db_module.record_invoice(
        tax_invoice_no="INV-001",
        customer_number="BETA456",
        ship_name="SAFE MARINE",
        inv_file_path="/tmp/beta456_inv001.pdf",
        invoice_date="2024-04-01",
        period_month="2024-04",
    )

    pending = db_module.get_invoices(
        customer_number="BETA456", period_month="2024-04", sent=0
    )
    assert len(pending) == 1
    invoice_row = pending[0]
    assert invoice_row["tax_invoice_no"] == "INV-001"
    assert invoice_row["customer_number"] == "BETA456"
    assert invoice_row["inv_file_path"] == "/tmp/beta456_inv001.pdf"

    sent_at = dt.datetime(2024, 5, 1, 12, 0, 0).isoformat()
    db_module.mark_invoice_sent(
        file_path="/tmp/beta456_inv001.pdf",
        sent_at=sent_at,
    )

    still_pending = db_module.get_invoices(
        customer_number="BETA456", period_month="2024-04", sent=0
    )
    assert still_pending == []

    sent = db_module.get_invoices(
        customer_number="BETA456", period_month="2024-04", sent=1
    )
    assert len(sent) == 1
    assert sent[0]["sent_at"] == sent_at
    assert sent[0]["send_error"] is None
