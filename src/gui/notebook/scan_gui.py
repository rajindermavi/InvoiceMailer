from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
import traceback

from src.backend.db.db import get_client_soa_summary, get_clients_by_head_offices
from src.backend.workflow import scan_for_invoices, get_excluded_invoices
from src.backend.db.db_utility import scan_clients_and_soa, scan_invoices_db

_CHECK = "☑"
_UNCHECK = "☐"


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

        # --- Button row ---
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=(10, 0))

        self.scan_clients_button = ttk.Button(
            btn_frame, text="Scan Clients", command=self.start_scan_clients
        )
        self.scan_clients_button.pack(side="left", padx=5)

        self.scan_invoices_button = ttk.Button(
            btn_frame, text="Scan Invoices", command=self.start_scan_invoices
        )
        self.scan_invoices_button.pack(side="left", padx=5)
        self.scan_invoices_button.state(["disabled"])

        # --- Status label ---
        self.scan_report_var = tk.StringVar()
        ttk.Label(
            frame,
            textvariable=self.scan_report_var,
            wraplength=800,
            justify="left",
        ).pack(fill="x", padx=5, pady=(5, 5))

        # --- Client pane (stage 1 results) ---
        client_frame = ttk.LabelFrame(frame, text="Clients & SOA")
        client_frame.pack(fill="both", expand=True, pady=(0, 5))

        client_columns = ("selected", "head_office", "head_office_name", "soa_found", "client_found")
        self.client_table = ttk.Treeview(
            client_frame, columns=client_columns, show="headings", height=8
        )
        for col, heading, width, anchor in [
            ("selected",        "✓",              35,  "center"),
            ("head_office",     "Head Office",    160, "w"),
            ("head_office_name","Head Office Name",220, "w"),
            ("soa_found",       "SOA Found",       90, "center"),
            ("client_found",    "On Client List", 110, "center"),
        ]:
            self.client_table.heading(col, text=heading)
            self.client_table.column(col, width=width, anchor=anchor, stretch=col not in ("selected", "soa_found", "client_found"))

        client_scroll = ttk.Scrollbar(client_frame, orient="vertical", command=self.client_table.yview)
        self.client_table.configure(yscrollcommand=client_scroll.set)
        self.client_table.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        client_scroll.pack(side="right", fill="y", pady=5, padx=(0, 5))

        self.client_table.bind("<ButtonRelease-1>", self._on_client_row_click)
        self._client_checked: dict[str, bool] = {}

        # --- Invoice pane (stage 2 results, with checkboxes) ---
        inv_frame = ttk.Frame(frame)
        inv_frame.pack(fill="both", expand=True, pady=(5, 0))

        _result_columns = (
            "client_aggregate",
            "head_office_name",
            "customer_number",
            "ship_name",
            "invoice_number",
            "invoice_date",
            "invoice_path",
            "soa_path",
        )
        _result_headings = (
            "Client Aggregate",
            "Head Office Name",
            "Customer Number",
            "Ship Name",
            "Invoice #",
            "Invoice Date",
            "Invoice File",
            "SOA File",
        )
        inv_columns = ("selected",) + _result_columns
        self.scan_table = ttk.Treeview(inv_frame, columns=inv_columns, show="headings")
        self.scan_table.heading("selected", text="✓")
        self.scan_table.column("selected", width=35, anchor="center", stretch=False)
        for col, heading in zip(_result_columns, _result_headings):
            self.scan_table.heading(col, text=heading)

        self.scan_table.bind("<ButtonRelease-1>", self._on_invoice_row_click)
        self._invoice_checked: dict[str, bool] = {}

        inv_scroll_y = ttk.Scrollbar(inv_frame, orient="vertical", command=self.scan_table.yview)
        inv_scroll_x = ttk.Scrollbar(inv_frame, orient="horizontal", command=self.scan_table.xview)
        self.scan_table.configure(yscrollcommand=inv_scroll_y.set, xscrollcommand=inv_scroll_x.set)
        inv_scroll_y.pack(side="right", fill="y", pady=(5, 0), padx=(0, 5))
        inv_scroll_x.pack(side="bottom", fill="x", padx=(5, 5))
        self.scan_table.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=(5, 0))

        # --- Excluded pane (invoices found but not included) ---
        excl_frame = ttk.LabelFrame(frame, text="Excluded")
        excl_frame.pack(fill="both", expand=True, pady=(5, 0))

        self.excl_table = ttk.Treeview(excl_frame, columns=_result_columns, show="headings")
        for col, heading in zip(_result_columns, _result_headings):
            self.excl_table.heading(col, text=heading)

        excl_scroll_y = ttk.Scrollbar(excl_frame, orient="vertical", command=self.excl_table.yview)
        excl_scroll_x = ttk.Scrollbar(excl_frame, orient="horizontal", command=self.excl_table.xview)
        self.excl_table.configure(yscrollcommand=excl_scroll_y.set, xscrollcommand=excl_scroll_x.set)
        excl_scroll_y.pack(side="right", fill="y", pady=(5, 0), padx=(0, 5))
        excl_scroll_x.pack(side="bottom", fill="x", padx=(5, 5))
        self.excl_table.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=(5, 0))

    # ------------------------------------------------------------------ #
    #  Checkbox toggles                                                    #
    # ------------------------------------------------------------------ #

    def _on_client_row_click(self, event):
        region = self.client_table.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.client_table.identify_column(event.x)
        if col != "#1":
            return
        item = self.client_table.identify_row(event.y)
        if not item:
            return
        values = list(self.client_table.item(item, "values"))
        head_office = values[1]
        new_state = not self._client_checked.get(head_office, True)
        self._client_checked[head_office] = new_state
        values[0] = _CHECK if new_state else _UNCHECK
        self.client_table.item(item, values=values)

    def _on_invoice_row_click(self, event):
        region = self.scan_table.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.scan_table.identify_column(event.x)
        if col != "#1":
            return
        item = self.scan_table.identify_row(event.y)
        if not item:
            return
        values = list(self.scan_table.item(item, "values"))
        invoice_number = values[5]  # invoice_number is index 5 after "selected"
        new_state = not self._invoice_checked.get(invoice_number, True)
        self._invoice_checked[invoice_number] = new_state
        values[0] = _CHECK if new_state else _UNCHECK
        self.scan_table.item(item, values=values)

    # ------------------------------------------------------------------ #
    #  Stage 1 — Scan Clients & SOA                                       #
    # ------------------------------------------------------------------ #

    def start_scan_clients(self):
        self.scan_clients_button.state(["disabled"])
        self.scan_invoices_button.state(["disabled"])
        self.generate_zip_button.state(["disabled"])
        self.start_send_button.state(["disabled"])
        self.scan_report_var.set("Scanning clients and SOA...")
        threading.Thread(target=self._scan_clients_thread, daemon=True).start()

    def _scan_clients_thread(self):
        try:
            workflow_kwargs = self._build_workflow_kwargs()
            skipped = scan_clients_and_soa(
                workflow_kwargs["client_directory"],
                workflow_kwargs["soa_folder"],
            )
            summary = get_client_soa_summary()
            self.root.after(0, lambda s=summary, w=skipped: self._on_clients_scan_complete(s, w))
        except Exception as exc:
            err_trace = traceback.format_exc()
            self.root.after(0, lambda e=exc, tb=err_trace: self._on_scan_error(e, tb))

    def _on_clients_scan_complete(self, summary: list[dict], skipped: list[str]):
        if skipped:
            self.scan_report_var.set("⚠ Files skipped:\n" + "\n".join(f"  • {w}" for w in skipped))
        else:
            self.scan_report_var.set(f"Client scan complete — {len(summary)} head office(s) found.")

        for row in self.client_table.get_children():
            self.client_table.delete(row)
        self._client_checked.clear()

        for entry in summary:
            ho = entry["head_office"]
            self._client_checked[ho] = True
            self.client_table.insert("", "end", values=(
                _CHECK,
                ho,
                entry.get("head_office_name", ""),
                "Yes" if entry["soa_found"] else "No",
                "Yes" if entry["client_found"] else "No",
            ))

        self.scan_clients_button.state(["!disabled"])
        self.scan_invoices_button.state(["!disabled"])

    # ------------------------------------------------------------------ #
    #  Stage 2 — Scan Invoices                                            #
    # ------------------------------------------------------------------ #

    def start_scan_invoices(self):
        self.scan_clients_button.state(["disabled"])
        self.scan_invoices_button.state(["disabled"])
        self._invoice_checked.clear()
        self.scan_report_var.set("Scanning invoices...")
        threading.Thread(target=self._scan_invoices_thread, daemon=True).start()

    def _scan_invoices_thread(self):
        try:
            workflow_kwargs = self._build_workflow_kwargs()
            period_month = workflow_kwargs["period_month"]
            period_year = workflow_kwargs["period_year"]
            if period_month is None or period_year is None:
                raise ValueError("Month and year are required for scanning invoices.")

            skipped = scan_invoices_db(workflow_kwargs["invoice_folder"])

            agg = workflow_kwargs["agg"]
            selected_head_offices = [ho for ho, checked in self._client_checked.items() if checked]
            client_list = get_clients_by_head_offices(selected_head_offices, agg)

            invoices_to_ship = scan_for_invoices(client_list, period_year, period_month, agg)
            rows = self._flatten_invoice_rows(invoices_to_ship)
            excl = self._flatten_excluded_rows(get_excluded_invoices(invoices_to_ship))
            self.root.after(0, lambda r=rows, x=excl, w=skipped: self._on_invoices_scan_complete(r, x, w))
        except Exception as exc:
            err_trace = traceback.format_exc()
            self.root.after(0, lambda e=exc, tb=err_trace: self._on_scan_error(e, tb))

    def _on_invoices_scan_complete(self, rows: list[tuple], excl: list[tuple], skipped: list[str]):
        if skipped:
            self.scan_report_var.set("⚠ Files skipped:\n" + "\n".join(f"  • {w}" for w in skipped))
        else:
            self.scan_report_var.set(
                f"Invoice scan complete — {len(rows)} included, {len(excl)} excluded."
            )
        self.update_scan_table(rows)
        self._update_excl_table(excl)
        self.scan_clients_button.state(["!disabled"])
        self.scan_invoices_button.state(["!disabled"])
        self.generate_zip_button.state(["!disabled"])
        self.start_send_button.state(["!disabled"])

    # ------------------------------------------------------------------ #
    #  Shared helpers                                                      #
    # ------------------------------------------------------------------ #

    def update_scan_table(self, rows):
        for row in self.scan_table.get_children():
            self.scan_table.delete(row)
        self._invoice_checked.clear()
        for r in rows:
            invoice_number = r[4]  # invoice_number is index 4 in the base tuple
            self._invoice_checked[invoice_number] = True
            self.scan_table.insert("", "end", values=(_CHECK,) + r)

    def _update_excl_table(self, rows):
        for row in self.excl_table.get_children():
            self.excl_table.delete(row)
        for r in rows:
            self.excl_table.insert("", "end", values=r)

    def _flatten_excluded_rows(self, excluded: list[dict]) -> list[tuple]:
        def _stem(p):
            return Path(p).stem if p else ""
        return [
            (
                inv.get("client_aggregate") or "",
                inv.get("head_office_name") or "",
                inv.get("customer_number") or "",
                inv.get("ship_name") or "",
                inv.get("invoice_number") or "",
                inv.get("invoice_date") or "",
                _stem(inv.get("invoice_path")),
                _stem(inv.get("soa_path")),
            )
            for inv in excluded
        ]

    def _flatten_invoice_rows(self, invoices_to_ship: dict) -> list[tuple]:
        """Return base tuples (no checkbox column) for the included invoice pane."""
        rows: list[tuple] = []

        def _stem(path_val: str | None) -> str:
            return Path(path_val).stem if path_val else ""

        for client, invoices in invoices_to_ship.items():
            for inv in invoices:
                rows.append((
                    client,
                    inv.get("head_office_name") or "",
                    inv.get("customer_number") or "",
                    inv.get("ship_name") or "",
                    inv.get("invoice_number") or "",
                    inv.get("invoice_date") or "",
                    _stem(inv.get("invoice_path")),
                    _stem(inv.get("soa_path")),
                ))
        return rows

    def _on_scan_error(self, exc: Exception, tb: str | None = None):
        self.scan_clients_button.state(["!disabled"])
        self.scan_invoices_button.state(["!disabled"])
        self.scan_report_var.set("")
        if tb:
            print(tb)
        messagebox.showerror("Scan Failed", str(exc))
