import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path
import re

from backend.config import SecureConfig
from gui.msal_device_code import MSalDeviceCodeTokenProvider
from gui.notebook.settings_gui import SettingsTab
from gui.notebook.email_gui import EmailSettingsTab
from gui.notebook.scan_gui import ScanTab
from gui.notebook.send_gui import SendTab
from gui.notebook.zip_gui import ZipTab
from gui.utility import load_settings, persist_settings, settings_from_vars, reset_month_and_year


class InvoiceMailerGUI(SettingsTab, EmailSettingsTab, ScanTab, ZipTab, SendTab):

    def __init__(self, root, secure_config: SecureConfig | None = None):
        self.root = root
        self.secure_config = secure_config or SecureConfig()
        self.settings = self.load_settings_from_store()
        self.msal_token_provider = self.init_msal_identity(
            self.secure_config,
            self.settings.get("ms_authority"),
        )
        if self.settings.get("ms_username"):
            self.msal_token_provider.ms_username = self.settings.get("ms_username")
        self.valid_ms_cached_token = self.validate_ms_cached_token(self.msal_token_provider)
        self.email_shipment: list[dict] = []
        self.root.title("Invoice Mailer")
        self.root.geometry("1000x800")

        # ---------------------------
        # Reset Month and Year Values
        # ---------------------------
        month_year_reset = {**self.settings, **reset_month_and_year()}
        self.persist_settings_to_store(month_year_reset)

        # -----------------------------
        # Header above tabs
        # -----------------------------
        header = ttk.Frame(self.root, padding=(10, 6))
        header.pack(fill="x")
        title_row = ttk.Frame(header)
        title_row.pack(fill="x")
        ttk.Label(title_row, text="Invoice Mailer", font=("TkDefaultFont", 14, "bold")).pack(side="left")
        ttk.Label(title_row, text="Scan, zip, and send invoices", foreground="#555").pack(side="left", padx=(8, 0))

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

    def init_msal_identity(self,secure_config: SecureConfig | None = None, authority: str | None = None) -> MSalDeviceCodeTokenProvider:
        secure_config = secure_config or SecureConfig()
        return MSalDeviceCodeTokenProvider(
            secure_config=secure_config,
            authority=authority,
            show_message=self._show_device_flow_popup,
        )

    def validate_ms_cached_token(self, token_provider: MSalDeviceCodeTokenProvider) -> bool:
        try:
            token_provider.acquire_token(interactive=False)
            return True
        except RuntimeError as e:
            print(e)
            return False

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
        is_keyring = getattr(self.secure_config, "is_keyring_backed", lambda: False)()
        msg = "All data securely encrypted!" if is_keyring else "Settings saved successfully!"
        messagebox.showinfo("Saved", msg)

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

        ms_auth_config = {
            "ms_smtp_host": settings.get("ms_smtp_host"),
            "ms_smtp_port": settings.get("ms_smtp_port"),
            "ms_use_starttls": settings.get("ms_use_starttls"),
            #"ms_username": settings.get("ms_username"),
            "ms_email_address": settings.get("ms_email_address"),
            #"ms_token_cache": settings.get("ms_token_cache"),
            #"ms_token_ts": settings.get("ms_token_ts"),
            "ms_authority": settings.get("ms_authority"),
        }
        if hasattr(self, "msal_token_provider") and hasattr(self.msal_token_provider, "set_authority"):
            self.msal_token_provider.set_authority(settings.get("ms_authority"))

        return {
            "invoice_folder": Path(required_paths["invoice_folder"]),
            "soa_folder": Path(required_paths["soa_folder"]),
            "client_directory": Path(required_paths["client_directory"]),
            "zip_output_dir": Path(settings["output_folder"]) if settings.get("output_folder") else None,
            "agg": settings.get("aggregate_by", "head_office"),
            "period_month": settings.get("email_month"),
            "period_year": settings.get("email_year"),
            "email_auth_method": settings.get("email_auth_method"),
            "smtp_config": {
                "host": settings.get("smtp_host"),
                "port": int(settings["smtp_port"]) if settings.get("smtp_port") else None,
                "username": settings.get("smtp_username"),
                "password": settings.get("smtp_password"),
                "from_addr": settings.get("smtp_from"),
                "use_tls": settings.get("smtp_use_tls", True),
            },
            "ms_auth_config": ms_auth_config,
            "email_setup": {
                "subject_template": settings.get("subject_template"),
                "body_template": settings.get("body_template"),
                "sender_name": settings.get("sender_name"),
                "reporter_emails": reporter_emails,
            },
            "mode": mode,
            "dry_run": mode == "Test",
        }

    def _show_device_flow_popup(self, message: object) -> None:
        """
        Show device-code instructions with selectable fields and copy buttons.
        Accepts either the MSAL flow dict or a plain string message.
        """
        def _show():
            flow_dict = message if isinstance(message, dict) else {}
            raw_text = flow_dict.get("message") if flow_dict else str(message)
            url, code = self._parse_device_flow_message(raw_text)
            url = flow_dict.get("verification_uri") or url
            code = flow_dict.get("user_code") or code
            message_text = raw_text or "Follow the sign-in instructions."

            popup = tk.Toplevel(self.root)
            popup.title("Microsoft Sign-in")
            popup.transient(self.root)
            popup.grab_set()

            container = ttk.Frame(popup, padding=10)
            container.pack(fill="both", expand=True)

            ttk.Label(
                container,
                text="Use a browser to open the website and enter the code to sign in.",
                wraplength=420,
                justify="left",
            ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

            ttk.Label(container, text="Website:").grid(row=1, column=0, sticky="e", padx=(0, 6), pady=4)
            url_var = tk.StringVar(value=url or "")
            url_entry = ttk.Entry(container, textvariable=url_var, width=50)
            url_entry.grid(row=1, column=1, sticky="we", pady=4)
            ttk.Button(container, text="Copy", command=lambda: self._copy_to_clipboard(url_var.get())).grid(row=1, column=2, padx=(6, 0), pady=4)

            ttk.Label(container, text="Code:").grid(row=2, column=0, sticky="e", padx=(0, 6), pady=4)
            code_var = tk.StringVar(value=code or "")
            code_entry = ttk.Entry(container, textvariable=code_var, width=30, font=("TkDefaultFont", 12, "bold"))
            code_entry.grid(row=2, column=1, sticky="w", pady=4)
            ttk.Button(container, text="Copy", command=lambda: self._copy_to_clipboard(code_var.get())).grid(row=2, column=2, padx=(6, 0), pady=4)

            ttk.Label(container, text="Full instructions:").grid(row=3, column=0, sticky="ne", padx=(0, 6), pady=(10, 0))
            text = tk.Text(container, height=4, width=55, wrap="word")
            text.insert("1.0", message_text)
            text.config(state="disabled")
            text.grid(row=3, column=1, columnspan=2, sticky="we", pady=(10, 0))

            container.columnconfigure(1, weight=1)
            url_entry.focus_set()

        # Ensure UI work happens on the main thread.
        if hasattr(self, "root"):
            self.root.after(0, _show)
        else:
            _show()

    def _copy_to_clipboard(self, value: str) -> None:
        if not value:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()

    def _parse_device_flow_message(self, message: str) -> tuple[str | None, str | None]:
        """
        Extract the sign-in URL and device code from the MSAL device-flow message.
        """
        url_match = re.search(r"https?://\S+", message)
        url = url_match.group(0) if url_match else None

        code_match = re.search(r"\b[A-Z0-9]{6,}\b", message)
        code = code_match.group(0) if code_match else None

        return url, code

def start_gui():
    root = tk.Tk()
    InvoiceMailerGUI(root)
    root.mainloop()
