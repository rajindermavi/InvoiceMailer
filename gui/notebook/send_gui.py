from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
import traceback

from backend.db.db import get_client_list
from backend.workflow import (
    db_mgmt,
    prep_and_send_emails,
    prep_invoice_zips,
    run_workflow,
    scan_for_invoices,
)


class SendTab:
    """
    Mixin that encapsulates the Send tab UI and behavior.
    Expects the consumer to define:
    - self.tab_send (ttk.Frame container)
    - self.root (tk.Tk)
    - self._build_workflow_kwargs() -> dict
    - self.email_shipment (list) to reuse generated shipments
    """

    def build_send_tab(self):
        frame = ttk.LabelFrame(self.tab_send, text="Send Emails")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.send_mode_label_var = tk.StringVar()
        self.send_mode_label = tk.Label(
            frame,
            textvariable=self.send_mode_label_var,
            font=("TkDefaultFont", 12, "bold"),
        )
        self.send_mode_label.pack(pady=(0, 5))
        self.update_send_mode_display()
        if hasattr(self, "mode_var"):
            self.mode_var.trace_add("write", lambda *_: self.update_send_mode_display())

        buttons = ttk.Frame(frame)
        buttons.pack(pady=10)

        self.start_send_button = ttk.Button(buttons, text="Start Email Send", command=self.start_send)
        self.start_send_button.pack(side="left", padx=(0, 5))

        self.clear_log_button = ttk.Button(buttons, text="Clear Text Screen", command=self.clear_send_log)
        self.clear_log_button.pack(side="left")

        self.progress = ttk.Progressbar(frame, length=300)
        self.progress.pack(pady=10)

        self.log_box = tk.Text(frame, height=20, width=80)
        self.log_box.pack(fill="both", expand=True, pady=10)

    def start_send(self):
        self.start_send_button.state(["disabled"])
        self.progress["value"] = 0
        threading.Thread(target=self._send_thread, daemon=True).start()

    def clear_send_log(self):
        self.log_box.delete("1.0", "end")
        self.progress["value"] = 0

    def _send_thread(self):
        self.root.after(0, lambda: self.log("Starting email send..."))
        try:
            workflow_kwargs = self._build_workflow_kwargs()
            period_month = workflow_kwargs["period_month"]
            period_year = workflow_kwargs["period_year"]
            if period_month is None or period_year is None:
                raise ValueError("Month and year are required for sending emails.")

            change_report = db_mgmt(
                workflow_kwargs["client_directory"],
                workflow_kwargs["invoice_folder"],
                workflow_kwargs["soa_folder"],
            )
            period_str = f"{int(period_year)}-{int(period_month):02d}"
            client_list = get_client_list(workflow_kwargs["agg"])

            if not self.email_shipment:
                invoices_to_ship = scan_for_invoices(client_list, period_str, workflow_kwargs["agg"])
                self.email_shipment = prep_invoice_zips(
                    invoices_to_ship,
                    workflow_kwargs.get("zip_output_dir"),
                )

            dry_run = workflow_kwargs.get("dry_run")
            if dry_run is None:
                dry_run = (workflow_kwargs.get("mode") or "").lower() == "test"

            email_report = prep_and_send_emails(
                workflow_kwargs["smtp_config"],
                workflow_kwargs["email_setup"],
                self.email_shipment,
                period_str,
                change_report,
                dry_run=dry_run,
            )
            self.root.after(0, lambda: self._on_send_complete(email_report, change_report))
        except Exception as exc:  # noqa: BLE001
            err = exc
            err_trace = traceback.format_exc()
            self.root.after(0, lambda e=err, tb=err_trace: self._on_send_error(e, tb))

    def log(self, msg):
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

    def _on_send_complete(self, email_report, change_report):
        self.progress["value"] = 100
        self.start_send_button.state(["!disabled"])
        self.log("Email send finished.")
        if change_report:
            self.log(f"Change report: {change_report}")
        if email_report:
            self.log(str(email_report))

    def _on_send_error(self, exc: Exception, tb: str | None = None):
        self.start_send_button.state(["!disabled"])
        self.progress["value"] = 0
        if tb:
            self.log(tb)
        else:
            self.log(str(exc))
        messagebox.showerror("Email Send Failed", str(exc))

    def handle_run_workflow(self):
        threading.Thread(
            target=self._run_workflow_thread, daemon=True
        ).start()

    def _run_workflow_thread(self):
        try:
            workflow_kwargs = self._build_workflow_kwargs()
            run_workflow(**workflow_kwargs)
            self.log("Workflow finished.")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Workflow Failed", str(exc))

    def update_send_mode_display(self):
        mode = getattr(self, "mode_var", None).get() if hasattr(self, "mode_var") else None
        if not mode:
            mode = getattr(self, "settings", {}).get("mode")
        mode = (mode or "Active").strip()
        if mode.lower() == "active":
            text = "Active - Emails will send"
            color = "red"
        else:
            text = "Test - Dry run (no emails sent)"
            color = "blue"
        if hasattr(self, "send_mode_label_var"):
            self.send_mode_label_var.set(text)
        if hasattr(self, "send_mode_label"):
            self.send_mode_label.config(fg=color)
