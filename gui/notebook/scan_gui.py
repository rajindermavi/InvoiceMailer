from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
import traceback

from backend.db.db import get_client_list
from backend.workflow import db_mgmt, scan_for_invoices


class ScanTab:
    """
    Mixin that encapsulates the Scan tab UI and behavior.
    Expects the consumer to define:
    - self.tab_scan (ttk.Frame container)
    - self.root (tk.Tk)
    - self._build_workflow_kwargs() -> dict
    """

    def build_scan_tab(self):
        frame = ttk.LabelFrame(self.tab_scan, text="Scan for Invoices")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.start_scan_button = ttk.Button(frame, text="Start Scan", command=self.start_scan)
        self.start_scan_button.pack(pady=(10, 0))

        self.change_report_var = tk.StringVar()
        ttk.Label(
            frame,
            textvariable=self.change_report_var,
            wraplength=800,
            justify="left"
        ).pack(fill="x", padx=5, pady=(5, 10))

        # Treeview for scan results
        columns = (
            "client_aggregate",
            "head_office_name",
            "customer_number",
            "ship_name",
            "invoice_number",
            "invoice_date",
            "invoice_path",
            "soa_path",
        )
        self.scan_table = ttk.Treeview(frame, columns=columns, show="headings")
        for col, heading in zip(
            columns,
            (
                "Client Aggregate",
                "Head Office Name",
                "Customer Number",
                "Ship Name",
                "Invoice #",
                "Invoice Date",
                "Invoice File",
                "SOA File",
            ),
        ):
            self.scan_table.heading(col, text=heading)
        self.scan_table.pack(fill="both", expand=True, pady=10)

    def start_scan(self):
        self.start_scan_button.state(["disabled"])
        self.change_report_var.set("Scanning...")
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        try:
            workflow_kwargs = self._build_workflow_kwargs()
            change_report = db_mgmt(
                workflow_kwargs["client_directory"],
                workflow_kwargs["invoice_folder"],
                workflow_kwargs["soa_folder"],
                force=True,
            )
            period_month = workflow_kwargs["period_month"]
            period_year = workflow_kwargs["period_year"]
            if period_month is None or period_year is None:
                raise ValueError("Month and year are required for scanning invoices.")

            period_str = f"{int(period_year)}-{int(period_month):02d}"
            client_list = get_client_list(workflow_kwargs["agg"])
            invoices_to_ship = scan_for_invoices(client_list, period_str, workflow_kwargs["agg"])
            rows = self._flatten_invoice_rows(invoices_to_ship)
            self.root.after(0, lambda: self._on_scan_complete(change_report, rows))
        except Exception as exc:  # noqa: BLE001
            err = exc
            err_trace = traceback.format_exc()
            self.root.after(0, lambda e=err, tb=err_trace: self._on_scan_error(e, tb))

    def update_scan_table(self, rows):
        # Clear table
        for row in self.scan_table.get_children():
            self.scan_table.delete(row)
        # Insert new
        for r in rows:
            self.scan_table.insert("", "end", values=r)

    def _flatten_invoice_rows(self, invoices_to_ship: dict) -> list[tuple]:
        rows: list[tuple] = []

        def _stem(path_val: str | None) -> str:
            return Path(path_val).stem if path_val else ""

        for client, invoices in invoices_to_ship.items():
            for inv in invoices:
                rows.append(
                    (
                        client,
                        inv.get("head_office_name") or "",
                        inv.get("customer_number") or "",
                        inv.get("ship_name") or "",
                        inv.get("invoice_number") or "",
                        inv.get("invoice_date") or "",
                        _stem(inv.get("invoice_path")),
                        _stem(inv.get("soa_path")),
                    )
                )
        return rows

    def _on_scan_complete(self, change_report: str | None, rows: list[tuple]):
        message = change_report or "Scan completed; no DB changes reported."
        self.change_report_var.set(message)
        self.update_scan_table(rows)
        self.start_scan_button.state(["!disabled"])

    def _on_scan_error(self, exc: Exception, tb: str | None = None):
        self.start_scan_button.state(["!disabled"])
        self.change_report_var.set("")
        if tb:
            print(tb)
        messagebox.showerror("Scan Failed", str(exc))
