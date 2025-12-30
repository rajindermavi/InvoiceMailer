from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
import traceback

from backend.workflow import prep_invoice_zips, scan_for_invoices
from backend.db.db import get_client_list
from backend.db.db_utility import db_mgmt


class ZipTab:
    """
    Mixin that encapsulates the Zip tab UI and behavior.
    Expects the consumer to define:
    - self.tab_preview (ttk.Frame container)
    - self.root (tk.Tk)
    - self._build_workflow_kwargs() -> dict
    - self.email_shipment (list) to store the generated shipment data
    """

    def build_zip_tab(self):
        frame = ttk.LabelFrame(self.tab_preview, text="ZIP Output")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.generate_zip_button = ttk.Button(frame, text="Generate ZIP", command=self.start_preview)
        self.generate_zip_button.pack(pady=10)
        self.preview_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.preview_status_var, wraplength=800, justify="left").pack(fill="x", padx=5)

        self.preview_table = ttk.Treeview(frame, columns=("client", "month", "zipfile"), show="headings")
        self.preview_table.heading("client", text="Client")
        self.preview_table.heading("month", text="Month")
        self.preview_table.heading("zipfile", text="ZIP Name")
        self.preview_table.pack(fill="both", expand=True, pady=10)

    def start_preview(self):
        self.generate_zip_button.state(["disabled"])
        self.preview_status_var.set("Generating ZIPs...")
        threading.Thread(target=self._preview_thread, daemon=True).start()

    def _preview_thread(self):
        try:
            workflow_kwargs = self._build_workflow_kwargs()
            db_mgmt(
                workflow_kwargs["client_directory"],
                workflow_kwargs["invoice_folder"],
                workflow_kwargs["soa_folder"],
            )
            period_month = workflow_kwargs["period_month"]
            period_year = workflow_kwargs["period_year"]
            if period_month is None or period_year is None:
                raise ValueError("Month and year are required for generating ZIPs.")

            period_str = f"{int(period_year)}-{int(period_month):02d}"
            client_list = get_client_list(workflow_kwargs["agg"])
            invoices_to_ship = scan_for_invoices(client_list, period_str, workflow_kwargs["agg"])
            email_shipment = prep_invoice_zips(invoices_to_ship, workflow_kwargs.get("zip_output_dir"))
            rows = [
                (
                    shipment.get("head_office_name") or Path(shipment["zip_path"]).stem,
                    period_str,
                    Path(shipment["zip_path"]).name,
                )
                for shipment in email_shipment
            ]
            self.email_shipment = email_shipment
            status_message = "ZIP generation complete."
            self.root.after(0, lambda: self._on_preview_complete(status_message, rows))
        except Exception as exc:  # noqa: BLE001
            err = exc
            err_trace = traceback.format_exc()
            self.root.after(0, lambda e=err, tb=err_trace: self._on_preview_error(e, tb))

    def update_preview_table(self, rows):
        for row in self.preview_table.get_children():
            self.preview_table.delete(row)
        for r in rows:
            self.preview_table.insert("", "end", values=r)

    def _on_preview_complete(self, status_message: str, rows: list[tuple]):
        self.preview_status_var.set(status_message)
        self.update_preview_table(rows)
        self.generate_zip_button.state(["!disabled"])

    def _on_preview_error(self, exc: Exception, tb: str | None = None):
        self.preview_status_var.set("")
        self.generate_zip_button.state(["!disabled"])
        if tb:
            print(tb)
        messagebox.showerror("ZIP Generation Failed", str(exc))
