import threading
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path

from backend.workflow import run_workflow
from backend.config import SecureConfig
from gui.notebook.settings_gui import SettingsTab
from gui.notebook.email_gui import EmailSettingsTab
from gui.notebook.scan_gui import ScanTab
from gui.utility import load_settings, persist_settings, settings_from_vars


class InvoiceMailerGUI(SettingsTab, EmailSettingsTab, ScanTab):

    def __init__(self, root, secure_config: SecureConfig | None = None):
        self.root = root
        self.secure_config = secure_config or SecureConfig()
        self.settings = self.load_settings_from_store()
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
        self.notebook.add(self.tab_preview, text="Preview")
        self.notebook.add(self.tab_send, text="Send & Logs")

        # -----------------------------
        # Build UI for each tab
        # -----------------------------
        self.build_settings_tab()
        self.build_email_tab()
        self.build_scan_tab()
        self.build_preview_tab()
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

        reporter_emails = settings.get("reporter_emails", [])
        if isinstance(reporter_emails, str):
            reporter_emails = [email.strip() for email in reporter_emails.split(",") if email.strip()]

        return {
            "invoice_folder": Path(required_paths["invoice_folder"]),
            "soa_folder": Path(required_paths["soa_folder"]),
            "client_directory": Path(required_paths["client_directory"]),
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
        }

    # ------------------------------------------------------------
    # PREVIEW TAB
    # ------------------------------------------------------------
    def build_preview_tab(self):
        frame = ttk.LabelFrame(self.tab_preview, text="Preview ZIP Output")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Button(frame, text="Generate ZIP Preview", command=self.start_preview).pack(pady=10)

        # Table for preview output
        self.preview_table = ttk.Treeview(frame, columns=("client", "month", "zipfile"), show="headings")
        self.preview_table.heading("client", text="Client")
        self.preview_table.heading("month", text="Month")
        self.preview_table.heading("zipfile", text="ZIP Name")
        self.preview_table.pack(fill="both", expand=True, pady=10)

    def start_preview(self):
        threading.Thread(target=self._preview_thread, daemon=True).start()

    def _preview_thread(self):
        # backend call: zipping.preview()
        # placeholder:
        demo_preview = [
            ("Client A", "2025-01", "ClientA_2025-01.zip"),
            ("Client B", "2025-01", "ClientB_2025-01.zip")
        ]
        self.update_preview_table(demo_preview)

    def update_preview_table(self, rows):
        for row in self.preview_table.get_children():
            self.preview_table.delete(row)
        for r in rows:
            self.preview_table.insert("", "end", values=r)

    # ------------------------------------------------------------
    # SEND TAB
    # ------------------------------------------------------------
    def build_send_tab(self):
        frame = ttk.LabelFrame(self.tab_send, text="Send Emails")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Button(frame, text="Start Email Send", command=self.start_send).pack(pady=10)

        # Progress bar
        self.progress = ttk.Progressbar(frame, length=300)
        self.progress.pack(pady=10)

        # Logs
        self.log_box = tk.Text(frame, height=20, width=80)
        self.log_box.pack(fill="both", expand=True, pady=10)

    def start_send(self):
        threading.Thread(target=self._send_thread, daemon=True).start()

    def _send_thread(self):
        # backend.emailer.send_all()
        self.log("Starting email send...")
        # Simulate progress
        for i in range(1, 101):
            self.progress["value"] = i
            self.root.update_idletasks()
        self.log("Emails sent!")

    def log(self, msg):
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

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

def start_gui():
    root = tk.Tk()
    InvoiceMailerGUI(root)
    root.mainloop()
