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

    add_or_update_client("CLIENT123", "client@example.com", name="ACME Corp")

    record_invoice(
        file_path=r"\\server\invoices\CLIENT123_2025-11-01_1234.pdf",
        client_code="CLIENT123",
        invoice_date="2025-11-01",
        period_month="2025-11",
    )

    unsent = get_unsent_invoices()
    for inv in unsent:
        print(inv["file_path"], inv["client_code"])

"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Optional

# Location of the DB file: <project_root>/data/invoice_mailer.sqlite3
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "invoice_mailer.sqlite3"


def _connect() -> sqlite3.Connection:
    """
    Return a SQLite connection with Row objects so you can access columns by name.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enforce foreign keys
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
    Create tables if they don't exist. Safe to call every time your program starts.
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
                emailforinvoice2    TEXT    NOT NULL,
                emailforinvoice3    TEXT    NOT NULL,
                emailforinvoice4    TEXT    NOT NULL,
                emailforinvoice5    TEXT    NOT NULL
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
                send_error          TEXT,      -- last error message, if any

                FOREIGN KEY (customer_number)
                    REFERENCES clients (customer_number)
                    ON UPDATE CASCADE
                    ON DELETE RESTRICT
            );
            """
        )

        # Table for soa
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS soa (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                head_office         TEXT    NOT NULL,
                soa_file_path       TEXT    NOT NULL UNIQUE,
                soa_date            TEXT,      -- ISO date string: YYYY-MM-DD
                soa_period_month    TEXT,      -- e.g. '2025-11' for grouping/zipping
                sent                INTEGER NOT NULL DEFAULT 0,  -- 0 = not sent, 1 = sent
                sent_at             TEXT,      -- ISO datetime string when successfully sent
                send_error          TEXT,      -- last error message, if any

                FOREIGN KEY (head_office)
                    REFERENCES clients (head_office)
                    ON UPDATE CASCADE
                    ON DELETE RESTRICT
            );
            """
        )

        # Helpful indexes
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_invoices_sent ON invoices(sent);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_invoices_client_month "
            "ON invoices(client_code, period_month);"
        )


def add_or_update_client(client_code: str, email: str, name: Optional[str] = None) -> None:
    """
    Insert a new client or update an existing client's name/email.

    client_code: code you infer from filename or config, used to group invoices.
    """
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO clients (client_code, name, email)
            VALUES (?, ?, ?)
            ON CONFLICT(client_code) DO UPDATE SET
                name  = COALESCE(excluded.name, clients.name),
                email = excluded.email;
            """,
            (client_code, name, email),
        )


def record_invoice(
    file_path: str,
    client_code: str,
    invoice_date: Optional[str] = None,  # "YYYY-MM-DD"
    period_month: Optional[str] = None,  # "YYYY-MM"
) -> None:
    """
    Insert a new invoice record if it doesn't already exist.

    If the invoice is already in the DB (same file_path), this is a no-op.
    """
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO invoices (
                client_code, file_path, invoice_date, period_month
            )
            VALUES (?, ?, ?, ?);
            """,
            (client_code, file_path, invoice_date, period_month),
        )


def get_unsent_invoices(
    client_code: Optional[str] = None,
    period_month: Optional[str] = None,
) -> list[sqlite3.Row]:
    """
    Return a list of unsent invoices (rows) as sqlite3.Row objects.

    You can use row["file_path"], row["client_code"], etc.

    Optional filters:
        client_code  – only invoices for that client
        period_month – e.g. '2025-11'
    """
    query = "SELECT * FROM invoices WHERE sent = 0"
    params: list[object] = []

    if client_code is not None:
        query += " AND client_code = ?"
        params.append(client_code)

    if period_month is not None:
        query += " AND period_month = ?"
        params.append(period_month)

    with get_conn() as conn:
        cur = conn.execute(query, params)
        return cur.fetchall()


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
                WHERE file_path = ?;
                """,
                (sent_at, file_path),
            )
        else:
            conn.execute(
                """
                UPDATE invoices
                SET send_error = ?
                WHERE file_path = ?;
                """,
                (error, file_path),
            )


def get_client_email(client_code: str) -> Optional[str]:
    """
    Return the email address for a client_code, or None if not found.
    """
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT email FROM clients WHERE client_code = ?;",
            (client_code,),
        )
        row = cur.fetchone()
        return row["email"] if row else None
