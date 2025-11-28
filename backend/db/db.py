"""
Simple local SQLite wrapper for the invoice mailer.

Usage example:

    from db import (
        init_db,
        add_or_update_client,
        record_invoice,
        get_unsent_invoices,
        mark_invoice_sent,
    )

    init_db()  # safe to call multiple times

    add_or_update_client(
        head_office="ACME Corp",
        customer_number="CLIENT123",
        emails=["client@example.com"],
    )

    record_invoice(
        tax_invoice_no="INV-001",
        customer_number="CLIENT123",
        ship_name="SAFE MARINE",
        invoice_file_path=r"\\server\invoices\CLIENT123_2025-11-01_1234.pdf",
        invoice_date="2025-11-01",
        period_month="2025-11",
    )

    unsent = get_unsent_invoices()
    for inv in unsent:
        print(inv["inv_file_path"], inv["customer_number"])

"""

from __future__ import annotations

import sqlite3
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Optional

from .db_path import get_db_path  # or from db import get_db_path if in same file

DB_PATH: Path = get_db_path()

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """
    Context manager that opens a connection and commits on success.

    Example:
        with get_conn() as conn:
            conn.execute("INSERT ...", params)
    """
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Create tables if they don't exist.
    """
    with get_conn() as conn:
        # Table for clients
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                head_office         TEXT    NOT NULL,
                customer_number     TEXT    NOT NULL UNIQUE,
                emailforinvoice1    TEXT    NOT NULL,
                emailforinvoice2    TEXT,
                emailforinvoice3    TEXT,
                emailforinvoice4    TEXT,
                emailforinvoice5    TEXT
            );
            """
        )

        # Table for soa
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS soa (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                head_office         TEXT    NOT NULL,
                head_office_name    TEXT,
                soa_file_path       TEXT    NOT NULL UNIQUE,
                soa_date            TEXT,      -- ISO date string: YYYY-MM-DD
                soa_period_month    TEXT,      -- e.g. '2025-11' for grouping/zipping
                sent                INTEGER NOT NULL DEFAULT 0,  -- 0 = not sent, 1 = sent
                sent_at             TEXT,      -- ISO datetime string when successfully sent
                send_error          TEXT       -- last error message, if any
            );
            """
        )

        # Table for invoices
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invoices (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                tax_invoice_no      TEXT    NOT NULL UNIQUE,
                customer_number     TEXT    NOT NULL,
                ship_name           TEXT    NOT NULL,
                inv_file_path       TEXT    NOT NULL UNIQUE,
                invoice_date        TEXT,      -- ISO date string: YYYY-MM-DD
                inv_period_month    TEXT,      -- e.g. '2025-11' for grouping/zipping
                sent                INTEGER NOT NULL DEFAULT 0,  -- 0 = not sent, 1 = sent
                sent_at             TEXT,      -- ISO datetime string when successfully sent
                send_error          TEXT       -- last error message, if any
            );
            """
        )

        # Helpful indexes
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_invoices_sent ON invoices(sent);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_invoices_client_month "
            "ON invoices(customer_number, inv_period_month);"
        )

# SQL WRITE

def add_or_update_client(
    head_office: str,
    customer_number: str,
    emails: Iterable[Optional[str]],
) -> None:
    """
    Insert a new client or update an existing client's invoice recipients.

    Pass up to five email addresses; only non-null/non-empty values are stored and
    any remaining slots are set to NULL.
    """
    email_list = [email for email in emails if email][:5]
    if len(email_list) < 5:
        email_list.extend([None] * (5 - len(email_list)))

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO clients (
                head_office,
                customer_number,
                emailforinvoice1,
                emailforinvoice2,
                emailforinvoice3,
                emailforinvoice4,
                emailforinvoice5
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(customer_number) DO UPDATE SET
                head_office = excluded.head_office,
                emailforinvoice1 = excluded.emailforinvoice1,
                emailforinvoice2 = excluded.emailforinvoice2,
                emailforinvoice3 = excluded.emailforinvoice3,
                emailforinvoice4 = excluded.emailforinvoice4,
                emailforinvoice5 = excluded.emailforinvoice5;
            """,
            (head_office, customer_number, *email_list),
        )

def add_or_update_soa(
    head_office: str,
    head_office_name: str,
    soa_file_path: str,
    soa_date: Optional[str] = None,
    soa_period_month: Optional[str] = None,
) -> None:
    """
    Insert or update a Statement of Account entry for the given client.

    The referenced client must exist, otherwise the foreign-key constraint on
    head_office will fail.
    """
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT 1 FROM clients WHERE head_office = ? LIMIT 1;",
            (head_office,),
        )
        client_exists = cur.fetchone() is not None
        if not client_exists:
            # Proceed with insert but signal the missing client to the caller.
            warnings.warn(
                f"Head office {head_office!r} does not exist in clients table; "
                "inserting SOA anyway.",
                stacklevel=2,
            )

        conn.execute(
            """
            INSERT INTO soa (head_office, head_office_name, soa_file_path, soa_date, soa_period_month)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(soa_file_path) DO UPDATE SET
                head_office = excluded.head_office,
                head_office_name = excluded.head_office_name,
                soa_date = excluded.soa_date,
                soa_period_month = excluded.soa_period_month;
            """,
            (head_office,head_office_name, soa_file_path, soa_date, soa_period_month),
        )

def record_invoice(
    tax_invoice_no: str,
    customer_number: str,
    ship_name: str,
    inv_file_path: str,
    invoice_date: Optional[str] = None,  # "YYYY-MM-DD"
    period_month: Optional[str] = None,  # "YYYY-MM"
) -> None:
    """
    Insert a new invoice record if it doesn't already exist (same invoice file path).
    """
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO invoices (
                tax_invoice_no,
                customer_number,
                ship_name,
                inv_file_path,
                invoice_date,
                inv_period_month
            )
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                tax_invoice_no,
                customer_number,
                ship_name,
                inv_file_path,
                invoice_date,
                period_month,
            ),
        )


def mark_invoice_sent(
    file_path: str,
    sent_at: str,
    error: Optional[str] = None,
) -> None:
    """
    Mark a single invoice as sent (or failed).

    If error is None, sent=1 and send_error cleared.
    If error is non-empty, sent stays 0 but send_error is stored.
    """
    with get_conn() as conn:
        if error is None:
            conn.execute(
                """
                UPDATE invoices
                SET sent = 1,
                    sent_at = ?,
                    send_error = NULL
                WHERE inv_file_path = ?;
                """,
                (sent_at, file_path),
            )
        else:
            conn.execute(
                """
                UPDATE invoices
                SET send_error = ?
                WHERE inv_file_path = ?;
                """,
                (error, file_path),
            )

# SQL READ

def get_client_list(
    client_type: Optional[str] = None 
) -> list[str]:
    
    if client_type == 'head_office':
        query = "SELECT distinct head_office FROM clients WHERE 1=1"
        client_type = 'head_office'
    
    if client_type == 'customer_number':
        query = "SELECT distinct customer_number FROM clients WHERE 1=1"
        client_type = 'customer_number'

    with get_conn() as conn:
        cur = conn.execute(query)
        return [r[client_type].strip() for r in cur.fetchall()]

def get_client(
    head_office: Optional[str] = None,
    customer_number: Optional[str] = None
) -> list[sqlite3.Row]:
    query = "SELECT * FROM clients WHERE 1=1"
    params: list[object] = []

    if head_office is not None:
        query += " AND head_office = ?"
        params.append(head_office)

    if customer_number is not None:
        query += " AND customer_number = ?"
        params.append(customer_number)

    with get_conn() as conn:
        cur = conn.execute(query, params)
        return cur.fetchall()

def get_invoices(
    head_office: Optional[str] = None,
    customer_number: Optional[str] = None,
    period_month: Optional[str] = None,
    sent: Optional[int] = None
) -> list[sqlite3.Row]:
    """
    Return a list of invoices (rows) as sqlite3.Row objects.

    Optional filters:
        head_office – match by the client's head_office (joins clients)
        customer_number  – only invoices for that client (customer_number column)
        period_month – e.g. '2025-11'
        sent
    """
    query = "SELECT inv.* FROM invoices inv"
    params: list[object] = []

    if head_office is not None:
        # Trim both sides to survive trailing spaces in client data.
        query += (
            " LEFT JOIN clients c"
            " ON TRIM(c.customer_number) = TRIM(inv.customer_number)"
        )

    query += " WHERE 1=1"

    if head_office is not None:
        query += " AND c.head_office = ?"
        params.append(head_office.strip())

    if customer_number is not None:
        query += " AND TRIM(inv.customer_number) = ?"
        params.append(customer_number.strip())

    if period_month is not None:
        query += " AND inv_period_month = ?"
        params.append(period_month)

    if sent is not None:
        query += " AND inv.sent = ?"
        params.append(sent)

    with get_conn() as conn:
        cur = conn.execute(query, params)
        return cur.fetchall()

def get_client_email(
    head_office: Optional[str] = None,
    customer_number: Optional[str] = None
) -> list[str]:
    """
    Return all invoice recipient emails for a customer_number. Empty if not found.
    Use head office only if emails are constant over head office.
    """

    query = (
        "SELECT "
        "emailforinvoice1, emailforinvoice2, emailforinvoice3, "
        "emailforinvoice4, emailforinvoice5 "
        "FROM clients "
        "WHERE 1 = 1"
    )
    params: list[object] = []

    if head_office is not None:
        query += " AND head_office = ?"
        params.append(head_office)

    if customer_number is not None:
        query += " AND customer_number = ?"
        params.append(customer_number)

    with get_conn() as conn:
        cur = conn.execute(query, params)
        row = cur.fetchone()
    
    return [email for email in row if email]

def get_soa_by_head_office(
    head_office: Optional[str] = None,
    head_office_name: Optional[str] = None,
    period_month: Optional[str] = None,
    sent: Optional[int] = None,
) -> list[sqlite3.Row]:
    """
    Return SOA rows filtered by head office, name, month, or sent status.
    """
    query = "SELECT * FROM soa WHERE 1=1"
    params: list[object] = []

    if head_office is not None:
        query += " AND TRIM(head_office) = ?"
        params.append(head_office.strip())

    if head_office_name is not None:
        query += " AND TRIM(head_office_name) = ?"
        params.append(head_office_name.strip())

    if period_month is not None:
        query += " AND soa_period_month = ?"
        params.append(period_month)

    if sent is not None:
        query += " AND sent = ?"
        params.append(sent)

    with get_conn() as conn:
        cur = conn.execute(query, params)
        return cur.fetchall()
