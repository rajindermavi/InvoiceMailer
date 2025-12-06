import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path

from backend.config import (
    SecureConfig,
    get_encrypted_config_path,
    get_key_path,
)
from backend.db.db_path import get_db_path
from backend.db.db_utility import mark_db_dirty
from gui.notebook.settings_gui import SettingsTab
from gui.notebook.email_gui import EmailSettingsTab
from gui.notebook.scan_gui import ScanTab
from gui.notebook.send_gui import SendTab
from gui.notebook.zip_gui import ZipTab
from gui.utility import apply_settings_to_vars, load_settings, persist_settings, settings_from_vars


class InvoiceMailerGUI(SettingsTab, EmailSettingsTab, ScanTab, ZipTab, SendTab):

    def __init__(self, root, secure_config: SecureConfig | None = None):
        self.root = root
        self.secure_config = secure_config or SecureConfig()
        self.settings = self.load_settings_from_store()
        self.email_shipment: list[dict] = []
        self.root.title("Invoice Mailer")
        self.root.geometry("1000x800")

        # -----------------------------
        # Header above tabs
        # -----------------------------
        header = ttk.Frame(self.root, padding=(10, 6))
        header.pack(fill="x")
        title_row = ttk.Frame(header)
        title_row.pack(fill="x")
        ttk.Label(title_row, text="Invoice Mailer", font=("TkDefaultFont", 14, "bold")).pack(side="left")
        ttk.Label(title_row, text="Scan, zip, and send invoices", foreground="#555").pack(side="left", padx=(8, 0))

        maintenance_row = ttk.Frame(header)
        maintenance_row.pack(fill="x", pady=(6, 0))
        ttk.Label(maintenance_row, text="Maintenance:").pack(side="left")
        ttk.Button(maintenance_row, text="Purge DB", command=self.purge_db).pack(side="left", padx=(6, 3))
        ttk.Button(maintenance_row, text="Purge Settings", command=self.purge_settings).pack(side="left", padx=3)

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

    # ---- Maintenance helpers ----
    def purge_db(self):
        db_path = get_db_path()
        backup_paths = list(db_path.parent.glob(db_path.name + ".bak*"))
        errors = []
        for path in [db_path, *backup_paths]:
            try:
                path.unlink(missing_ok=True)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{path}: {exc}")

        mark_db_dirty()

        if errors:
            messagebox.showerror("Purge DB", "Failed to remove some files:\n" + "\n".join(errors))
            return

        if hasattr(self, "change_report_var"):
            self.change_report_var.set("Database purged; run Scan to rebuild.")
        if hasattr(self, "update_scan_table"):
            self.update_scan_table([])
        messagebox.showinfo("Purge DB", "Database files removed. Run Scan to rebuild the database.")

    def purge_settings(self):
        cfg_path = get_encrypted_config_path()
        key_path = get_key_path()
        errors = []
        for path in (cfg_path, key_path):
            try:
                path.unlink(missing_ok=True)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{path}: {exc}")

        # Reload defaults into the form if available.
        self.settings = self.load_settings_from_store()
        if hasattr(self, "_settings_vars"):
            apply_settings_to_vars(self._settings_vars, self.settings)
        if hasattr(self, "_email_settings_vars"):
            apply_settings_to_vars(self._email_settings_vars, self.settings)
        if hasattr(self, "update_current_settings_display"):
            self.update_current_settings_display()
        if hasattr(self, "update_email_settings_display"):
            self.update_email_settings_display()

        if errors:
            messagebox.showerror("Purge Settings", "Settings cleared, but some files could not be removed:\n" + "\n".join(errors))
        else:
            messagebox.showinfo("Purge Settings", "Encrypted settings removed and defaults restored.")

def start_gui():
    root = tk.Tk()
    InvoiceMailerGUI(root)
    root.mainloop()
