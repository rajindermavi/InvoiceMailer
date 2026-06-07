from __future__ import annotations

import datetime as dt

import pytest

import src.backend.db.db as db_module


@pytest.fixture
def initialized_db(monkeypatch, tmp_path):
    """Point the DB module at a temporary SQLite file and create schema."""
    temp_path = tmp_path / "invoice_mailer.sqlite3"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("APP_DB_PATH", str(temp_path))
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


def test_record_invoice_and_query_invoice(initialized_db):
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

    invoices = db_module.get_invoices(
        customer_number="BETA456", period_month="2024-04"
    )
    assert len(invoices) == 1
    invoice_row = invoices[0]
    assert invoice_row["tax_invoice_no"] == "INV-001"
    assert invoice_row["customer_number"] == "BETA456"
    assert invoice_row["inv_file_path"] == "/tmp/beta456_inv001.pdf"
    assert invoice_row["ship_name"] == "SAFE MARINE"
    assert invoice_row["invoice_date"] == "2024-04-01"
    assert invoice_row["inv_period_month"] == "2024-04"
