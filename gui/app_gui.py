import threading
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path
import traceback

from backend.workflow import (
    db_mgmt,
    prep_and_send_emails,
    prep_invoice_zips,
    run_workflow,
    scan_for_invoices,
)
from backend.db.db import get_client_list
from backend.config import SecureConfig
from gui.notebook.settings_gui import SettingsTab
from gui.notebook.email_gui import EmailSettingsTab
from gui.notebook.scan_gui import ScanTab
from gui.notebook.zip_gui import ZipTab
from gui.utility import load_settings, persist_settings, settings_from_vars


class InvoiceMailerGUI(SettingsTab, EmailSettingsTab, ScanTab, ZipTab):

    def __init__(self, root, secure_config: SecureConfig | None = None):
        self.root = root
        self.secure_config = secure_config or SecureConfig()
        self.settings = self.load_settings_from_store()
        self.email_shipment: list[dict] = []
        self.root.title("Invoice Mailer")
        self.root.geometry("900x650")

        # -----------------------------
        # Notebook (Tabs)
        # -----------------------------
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        self.tab_settings = ttk.Frame(self.notebook)
        self.tab_email = ttk.Frame(self.notebook)
        self.tab_scan = ttk.Frame(self.notebook)
        self.tab_preview = ttk.Frame(self.notebook)
        self.tab_send = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_settings, text="Settings")
        self.notebook.add(self.tab_email, text="Email Settings")
        self.notebook.add(self.tab_scan, text="Scan")
        self.notebook.add(self.tab_preview, text="Zip")
        self.notebook.add(self.tab_send, text="Send & Logs")

        # -----------------------------
        # Build UI for each tab
        # -----------------------------
        self.build_settings_tab()
        self.build_email_tab()
        self.build_scan_tab()
        self.build_zip_tab()
        self.build_send_tab()

    # ---- Settings helpers shared across tabs ----
    def load_settings_from_store(self):
        self.settings = load_settings(self.secure_config)
        return self.settings

    def persist_settings_to_store(self, settings):
        persist_settings(self.secure_config, settings)
        self.settings = dict(settings)

    def save_settings(self):
        base_settings = settings_from_vars(self._settings_vars) if hasattr(self, "_settings_vars") else {}
        email_settings = settings_from_vars(self._email_settings_vars) if hasattr(self, "_email_settings_vars") else {}
        if hasattr(self, "body_template_text"):
            email_settings["body_template"] = self.body_template_text.get("1.0", "end").strip()
        new_settings = {**base_settings, **email_settings}
        self.persist_settings_to_store(new_settings)
        if hasattr(self, "update_current_settings_display"):
            self.update_current_settings_display()
        if hasattr(self, "update_email_settings_display"):
            self.update_email_settings_display()
        if hasattr(self, "update_send_mode_display"):
            self.update_send_mode_display()
        messagebox.showinfo("Saved", "Settings saved successfully!")

    def _build_workflow_kwargs(self) -> dict:
        # Merge persisted settings with any current edits on the form.
        settings = dict(getattr(self, "settings", {}))
        if hasattr(self, "_settings_vars"):
            settings.update(settings_from_vars(self._settings_vars))
        if hasattr(self, "_email_settings_vars"):
            settings.update(settings_from_vars(self._email_settings_vars))

        required_paths = {
            "invoice_folder": settings.get("invoice_folder"),
            "soa_folder": settings.get("soa_folder"),
            "client_directory": settings.get("client_file"),
        }
        missing = [name for name, path in required_paths.items() if not path]
        if missing:
            raise ValueError(f"Missing required settings: {', '.join(missing)}")

        mode = settings.get("mode", "Active")
        reporter_emails = settings.get("reporter_emails", [])
        if isinstance(reporter_emails, str):
            reporter_emails = [email.strip() for email in reporter_emails.split(",") if email.strip()]

        return {
            "invoice_folder": Path(required_paths["invoice_folder"]),
            "soa_folder": Path(required_paths["soa_folder"]),
            "client_directory": Path(required_paths["client_directory"]),
            "zip_output_dir": Path(settings["output_folder"]) if settings.get("output_folder") else None,
            "agg": settings.get("aggregate_by", "head_office"),
            "period_month": settings.get("email_month"),
            "period_year": settings.get("email_year"),
            "smtp_config": {
                "host": settings.get("smtp_host"),
                "port": int(settings["smtp_port"]) if settings.get("smtp_port") else None,
                "username": settings.get("smtp_username"),
                "password": settings.get("smtp_password"),
                "from_addr": settings.get("smtp_from"),
                "use_tls": settings.get("smtp_use_tls", True),
            },
            "email_setup": {
                "subject_template": settings.get("subject_template"),
                "body_template": settings.get("body_template"),
                "sender_name": settings.get("sender_name"),
                "reporter_emails": reporter_emails,
            },
            "mode": mode,
            "dry_run": mode == "Test",
        }

    # ------------------------------------------------------------
    # SEND TAB
    # ------------------------------------------------------------
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

        self.start_send_button = ttk.Button(frame, text="Start Email Send", command=self.start_send)
        self.start_send_button.pack(pady=10)

        # Progress bar
        self.progress = ttk.Progressbar(frame, length=300)
        self.progress.pack(pady=10)

        # Logs
        self.log_box = tk.Text(frame, height=20, width=80)
        self.log_box.pack(fill="both", expand=True, pady=10)

    def start_send(self):
        self.start_send_button.state(["disabled"])
        self.progress["value"] = 0
        threading.Thread(target=self._send_thread, daemon=True).start()

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

def start_gui():
    root = tk.Tk()
    InvoiceMailerGUI(root)
    root.mainloop()
