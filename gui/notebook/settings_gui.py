from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
import threading
from email.message import EmailMessage

from gui.msal_device_code import send_email_via_graph
from gui.utility import apply_settings_to_vars, settings_from_vars


class SettingsTab:
    """
    Mixin that encapsulates the Settings tab UI and behavior.
    Expects the consumer to define:
    - self.tab_settings (ttk.Frame container)
    - self.secure_config (SecureConfig instance)
    - self.settings (dict)
    - self.root (tk.Tk)
    """

    def build_settings_tab(self):
        container = ttk.Frame(self.tab_settings)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        frame = ttk.LabelFrame(container, text="Configuration")
        frame.pack(fill="x", padx=5, pady=(0, 10))

        # Invoice folder
        ttk.Label(frame, text="Invoice Folder:").grid(row=0, column=0, sticky="w")
        self.invoice_folder_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.invoice_folder_var, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(frame, text="Browse", command=self.pick_invoice_folder).grid(row=0, column=2, padx=5)

        # SOA folder
        ttk.Label(frame, text="SOA Folder:").grid(row=1, column=0, sticky="w")
        self.soa_folder_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.soa_folder_var, width=50).grid(row=1, column=1, padx=5)
        ttk.Button(frame, text="Browse", command=self.pick_soa_folder).grid(row=1, column=2, padx=5)

        # Client list
        ttk.Label(frame, text="Client List File:").grid(row=2, column=0, sticky="w")
        self.client_file_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.client_file_var, width=50).grid(row=2, column=1, padx=5)
        ttk.Button(frame, text="Browse", command=self.pick_client_file).grid(row=2, column=2, padx=5)

        # Output ZIP folder
        ttk.Label(frame, text="ZIP Output Folder:").grid(row=3, column=0, sticky="w")
        self.output_folder_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.output_folder_var, width=50).grid(row=3, column=1, padx=5)
        ttk.Button(frame, text="Browse", command=self.pick_output_folder).grid(row=3, column=2, padx=5)

        # Aggregate by (hidden; retained for settings/summary only)
        self.aggregate_by_var = tk.StringVar(value="head_office")

        # Mode (dev/prod)
        ttk.Label(frame, text="Mode:").grid(row=4, column=0, sticky="w")
        self.mode_var = tk.StringVar(value="Active")
        ttk.Combobox(frame, textvariable=self.mode_var, values=["Active", "Test"], width=10).grid(row=4, column=1, sticky="w")

        # Email authentication method toggle
        self.email_auth_method_var = tk.StringVar(value="smtp")
        self._auth_frame_pack_opts = {"fill": "x", "padx": 5, "pady": (0, 10)}

        auth_frame = ttk.LabelFrame(container, text="Authentication")
        auth_frame.pack(**self._auth_frame_pack_opts)
        ttk.Radiobutton(auth_frame, text="SMTP", variable=self.email_auth_method_var, value="smtp", command=self._refresh_auth_frames).grid(
            row=0, column=0, padx=5, pady=2, sticky="w"
        )
        ttk.Radiobutton(auth_frame, text="MS Auth", variable=self.email_auth_method_var, value="ms_auth", command=self._refresh_auth_frames).grid(
            row=0, column=1, padx=5, pady=2, sticky="w"
        )

        self.smtp_host_var = tk.StringVar(value="smtp.gmail.com")
        self.smtp_port_var = tk.StringVar(value="587")
        self.smtp_username_var = tk.StringVar()
        self.smtp_password_var = tk.StringVar()
        self.smtp_from_var = tk.StringVar()
        self.smtp_use_tls_var = tk.BooleanVar(value=True)
        self.ms_username_var = tk.StringVar()
        self.ms_email_address_var = tk.StringVar()
        self.ms_token_cache_var = tk.StringVar()
        self.ms_token_ts_var = tk.StringVar()

        self._settings_vars = {
            "invoice_folder": self.invoice_folder_var,
            "soa_folder": self.soa_folder_var,
            "client_file": self.client_file_var,
            "output_folder": self.output_folder_var,
            "aggregate_by": self.aggregate_by_var,
            "mode": self.mode_var,
            "email_auth_method": self.email_auth_method_var,
            "smtp_host": self.smtp_host_var,
            "smtp_port": self.smtp_port_var,
            "smtp_username": self.smtp_username_var,
            "smtp_password": self.smtp_password_var,
            "smtp_from": self.smtp_from_var,
            "smtp_use_tls": self.smtp_use_tls_var,
            "ms_username": self.ms_username_var,
            "ms_email_address": self.ms_email_address_var,
            "ms_token_cache": self.ms_token_cache_var,
            "ms_token_ts": self.ms_token_ts_var,
        }
        apply_settings_to_vars(self._settings_vars, self.settings)

        self.auth_content = ttk.Frame(container)
        self.auth_content.pack(**self._auth_frame_pack_opts)

        self.smtp_frame = ttk.LabelFrame(self.auth_content, text="SMTP")
        self.ms_auth_frame = ttk.LabelFrame(self.auth_content, text="MS Auth")
        self.ms_auth_status_var = tk.StringVar(value="MS Token: (not requested)")
        self.fetch_ms_token_button = ttk.Button(self.ms_auth_frame, text="Fetch MS Auth Token", command=self.fetch_ms_auth_token)
        self.fetch_ms_token_button.grid(row=0, column=0, padx=5, pady=2, sticky="w")
        #ttk.Label(self.ms_auth_frame, textvariable=self.ms_auth_status_var, foreground="#555").grid(row=0, column=1, sticky="w")
        ttk.Label(self.ms_auth_frame, text="MS Email Address:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Entry(self.ms_auth_frame, textvariable=self.ms_email_address_var, width=40).grid(row=1, column=1, padx=5, pady=2, sticky="w")
        self.send_ms_test_button = ttk.Button(self.ms_auth_frame, text="Send Test Email", command=self.send_ms_test_email)
        self.send_ms_test_button.grid(row=2, column=0, padx=5, pady=2, sticky="w")

        ttk.Label(self.smtp_frame, text="Host:").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.smtp_frame, textvariable=self.smtp_host_var, width=40).grid(row=0, column=1, padx=5, sticky="w")

        ttk.Label(self.smtp_frame, text="Port:").grid(row=1, column=0, sticky="w")
        ttk.Entry(self.smtp_frame, textvariable=self.smtp_port_var, width=10).grid(row=1, column=1, padx=5, sticky="w")

        ttk.Label(self.smtp_frame, text="Username:").grid(row=2, column=0, sticky="w")
        ttk.Entry(self.smtp_frame, textvariable=self.smtp_username_var, width=40).grid(row=2, column=1, padx=5, sticky="w")

        ttk.Label(self.smtp_frame, text="Password:").grid(row=3, column=0, sticky="w")
        ttk.Entry(self.smtp_frame, textvariable=self.smtp_password_var, show="*", width=40).grid(row=3, column=1, padx=5, sticky="w")

        ttk.Label(self.smtp_frame, text="From Address:").grid(row=4, column=0, sticky="w")
        ttk.Entry(self.smtp_frame, textvariable=self.smtp_from_var, width=40).grid(row=4, column=1, padx=5, sticky="w")

        ttk.Checkbutton(self.smtp_frame, text="Use TLS", variable=self.smtp_use_tls_var).grid(row=5, column=0, columnspan=2, sticky="w")

        self._refresh_auth_frames()

        ttk.Button(container, text="Save Settings", command=self.save_settings).pack(fill="x", padx=5, pady=(0, 10))

        current_frame = ttk.LabelFrame(container, text="Current Settings")
        current_frame.pack(fill="x", padx=5, pady=(0, 5))
        current_frame.columnconfigure(0, weight=1)
        current_frame.columnconfigure(1, weight=1)

        self.invoice_folder_label_var = tk.StringVar(value="Invoice Folder: (not saved)")
        self.output_folder_label_var = tk.StringVar(value="ZIP Output Folder: (not saved)")
        self.client_file_label_var = tk.StringVar(value="Client List File: (not saved)")
        self.soa_folder_label_var = tk.StringVar(value="SOA Folder: (not saved)")
        self.aggregate_by_label_var = tk.StringVar(value="Aggregate By: (not saved)")
        self.mode_label_var = tk.StringVar(value="Mode: (not saved)")
        self.auth_method_label_var = tk.StringVar(value="Email Auth: (not saved)")
        self.smtp_host_label_var = tk.StringVar(value="SMTP Host: (not saved)")
        self.smtp_port_label_var = tk.StringVar(value="SMTP Port: (not saved)")
        self.smtp_username_label_var = tk.StringVar(value="SMTP Username: (not saved)")
        self.smtp_password_label_var = tk.StringVar(value="SMTP Password: (not saved)")
        self.smtp_from_label_var = tk.StringVar(value="From Address: (not saved)")
        self.smtp_tls_label_var = tk.StringVar(value="Use TLS: (not saved)")
        self.ms_username_label_var = tk.StringVar(value="MS Username: (not saved)")
        self.ms_email_address_label_var = tk.StringVar(value="MS Email Address: (not saved)")
        self.ms_token_cache_label_var = tk.StringVar(value="MS Token Cache: (not saved)")
        self.ms_token_ts_label_var = tk.StringVar(value="MS Token Timestamp: (not saved)")
        self.ms_token_valid_label_var = tk.StringVar(value="MS Token Valid: (not checked)")

        cfg_summary = ttk.Frame(current_frame)
        cfg_summary.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ttk.Label(cfg_summary, textvariable=self.invoice_folder_label_var).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.soa_folder_label_var).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.client_file_label_var).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.output_folder_label_var).grid(row=3, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.aggregate_by_label_var).grid(row=4, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.mode_label_var).grid(row=5, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.auth_method_label_var).grid(row=6, column=0, sticky="w", pady=2)

        self.smtp_summary = ttk.Frame(current_frame)
        self.smtp_summary.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ttk.Label(self.smtp_summary, textvariable=self.smtp_host_label_var).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(self.smtp_summary, textvariable=self.smtp_port_label_var).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Label(self.smtp_summary, textvariable=self.smtp_username_label_var).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Label(self.smtp_summary, textvariable=self.smtp_password_label_var).grid(row=3, column=0, sticky="w", pady=2)
        ttk.Label(self.smtp_summary, textvariable=self.smtp_from_label_var).grid(row=4, column=0, sticky="w", pady=2)
        #ttk.Label(self.smtp_summary, textvariable=self.smtp_tls_label_var).grid(row=5, column=0, sticky="w", pady=2)

        self.ms_summary = ttk.Frame(current_frame)
        self.ms_summary.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ttk.Label(self.ms_summary, textvariable=self.ms_username_label_var).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(self.ms_summary, textvariable=self.ms_email_address_label_var).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Label(self.ms_summary, textvariable=self.ms_token_cache_label_var).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Label(self.ms_summary, textvariable=self.ms_token_ts_label_var).grid(row=3, column=0, sticky="w", pady=2)
        ttk.Label(self.ms_summary, textvariable=self.ms_token_valid_label_var).grid(row=4, column=0, sticky="w", pady=2)

        self.update_current_settings_display()

    def _refresh_auth_frames(self, *_):
        # Toggle between SMTP and MS Auth frames based on the selected method.
        selected = self.email_auth_method_var.get()
        self.smtp_frame.pack_forget()
        self.ms_auth_frame.pack_forget()
        if selected == "ms_auth":
            self.ms_auth_frame.pack(fill="x")
        else:
            self.smtp_frame.pack(fill="x")
        if hasattr(self, "smtp_summary") and hasattr(self, "ms_summary"):
            self._refresh_current_summary_frames()

    def pick_invoice_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.invoice_folder_var.set(folder)

    def pick_output_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_folder_var.set(folder)

    def pick_soa_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.soa_folder_var.set(folder)

    def pick_client_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel/CSV", "*.xlsx *.csv"), ("All files", "*.*")])
        if file_path:
            self.client_file_var.set(file_path)

    def save_settings(self):
        raise NotImplementedError("save_settings should be implemented by the parent class.")

    def update_current_settings_display(self):
        # Merge the current tab values into the existing settings so we don't
        # clobber email-related defaults before the Email tab is built.
        base_settings = settings_from_vars(self._settings_vars)
        self.settings = {**getattr(self, "settings", {}), **base_settings}

        self.invoice_folder_label_var.set(f"Invoice Folder: {self.settings['invoice_folder'] or '(empty)'}")
        self.soa_folder_label_var.set(f"SOA Folder: {self.settings['soa_folder'] or '(empty)'}")
        self.output_folder_label_var.set(f"ZIP Output Folder: {self.settings['output_folder'] or '(empty)'}")
        self.client_file_label_var.set(f"Client List File: {self.settings['client_file'] or '(empty)'}")
        self.aggregate_by_label_var.set(f"Aggregate By: {self.settings['aggregate_by'].replace('_',' ').title() or '(empty)'}")
        self.mode_label_var.set(f"Mode: {self.settings['mode'] or '(empty)'}")
        #auth_method_raw = (self.settings.get('email_auth_method') or 'smtp').lower()
        #auth_method_label = "MS Auth" if auth_method_raw == "ms_auth" else "SMTP"
        auth_method_label = self.email_auth_method_var.get()
        self.auth_method_label_var.set(f"Email Auth: {auth_method_label}")
        self.smtp_host_label_var.set(f"SMTP Host: {self.settings['smtp_host'] or '(empty)'}")
        self.smtp_port_label_var.set(f"SMTP Port: {self.settings['smtp_port'] or '(empty)'}")
        self.smtp_username_label_var.set(f"SMTP Username: {self.settings['smtp_username'] or '(empty)'}")
        masked_pwd = "*" * len(self.settings['smtp_password']) if self.settings['smtp_password'] else "(empty)"
        self.smtp_password_label_var.set(f"SMTP Password: {masked_pwd}")
        self.smtp_from_label_var.set(f"From Address: {self.settings['smtp_from'] or '(empty)'}")
        self.smtp_tls_label_var.set(f"Use TLS: {'Yes' if self.settings['smtp_use_tls'] else 'No'}")
        cache_value = self.settings.get("ms_token_cache") or ""
        cache_label = "(saved)" if cache_value else "(empty)"
        ts_label = self.settings.get("ms_token_ts") or "(NA)"
        ms_username_label = self.settings.get("ms_username") or "(empty)"
        ms_email_label = self.settings.get("ms_email_address") or "(empty)"
        self.ms_username_label_var.set(f"MS Username: {ms_username_label}")
        self.ms_email_address_label_var.set(f"MS Email Address: {ms_email_label}")
        self.ms_token_cache_label_var.set(f"MS Token Cache: {cache_label}")
        self.ms_token_ts_label_var.set(f"MS Token Timestamp: {ts_label}")
        is_valid = getattr(self, "valid_ms_cached_token", None)
        if is_valid is True:
            valid_label = "Yes"
        elif is_valid is False:
            valid_label = "No"
        else:
            valid_label = "(unknown)"
        self.ms_token_valid_label_var.set(f"MS Token Valid: {valid_label}")
        self._refresh_current_summary_frames()

    def _refresh_current_summary_frames(self):
        selected = self.email_auth_method_var.get()
        self.smtp_summary.grid_remove()
        self.ms_summary.grid_remove()
        if selected == "ms_auth":
            self.ms_summary.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        else:
            self.smtp_summary.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

    def fetch_ms_auth_token(self):
        if getattr(self, "_ms_auth_in_progress", False):
            return

        if not hasattr(self, "msal_token_provider"):
            messagebox.showerror("MS Auth", "MSAL token provider is not configured.")
            return

        self._ms_auth_in_progress = True
        if getattr(self, "fetch_ms_token_button", None):
            self.fetch_ms_token_button.state(["disabled"])

        ms_username = self.ms_username_var.get().strip()
        if ms_username:
            self.msal_token_provider.ms_username = ms_username

        self.ms_auth_status_var.set("MS Token: waiting for sign-in...")

        def _worker():
            try:
                self.msal_token_provider.acquire_token(interactive=True)
            except Exception as exc:
                self.root.after(0, self._handle_ms_auth_failure, exc)
                return
            provider_username = getattr(self.msal_token_provider, "ms_username", None)
            self.root.after(0, self._handle_ms_auth_success, provider_username or ms_username)

        threading.Thread(target=_worker, daemon=True).start()

    def _handle_ms_auth_success(self, ms_username: str | None) -> None:
        if not ms_username:
            ms_username = getattr(self.msal_token_provider, "ms_username", None)
        if ms_username:
            self.ms_username_var.set(ms_username)
        timestamp = datetime.now().isoformat(timespec="seconds")
        self.ms_token_ts_var.set(timestamp)
        self.valid_ms_cached_token = True
        self.ms_auth_status_var.set("MS Token: cached")
        self._persist_ms_auth_status(ms_username, timestamp)
        self.update_current_settings_display()
        if getattr(self, "fetch_ms_token_button", None):
            self.fetch_ms_token_button.state(["!disabled"])
        self._ms_auth_in_progress = False
        messagebox.showinfo("MS Auth", "MS token acquired and cached.")

    def _handle_ms_auth_failure(self, exc: Exception) -> None:
        self.valid_ms_cached_token = False
        self.ms_auth_status_var.set("MS Token: failed to acquire")
        self.update_current_settings_display()
        if getattr(self, "fetch_ms_token_button", None):
            self.fetch_ms_token_button.state(["!disabled"])
        self._ms_auth_in_progress = False
        messagebox.showerror("MS Auth", f"Could not obtain MS token:\n{exc}")

    def _persist_ms_auth_status(self, ms_username: str, timestamp: str) -> None:
        if not hasattr(self, "secure_config") or not self.secure_config:
            return
        data = self.secure_config.load() or {}
        if ms_username:
            data["ms_username"] = ms_username
        ms_email = getattr(self, "ms_email_address_var", None)
        if ms_email:
            data["ms_email_address"] = ms_email.get()
        if timestamp:
            data["ms_token_ts"] = timestamp
        self.secure_config.save(data)

    def send_ms_test_email(self) -> None:
        if getattr(self, "_ms_test_in_progress", False):
            return

        ms_email = self.ms_email_address_var.get().strip()
        if not ms_email:
            messagebox.showerror("MS Auth", "Please enter an MS Email Address before sending a test email.")
            return
        if not hasattr(self, "msal_token_provider"):
            messagebox.showerror("MS Auth", "MSAL token provider is not configured.")
            return

        self._ms_test_in_progress = True
        if getattr(self, "send_ms_test_button", None):
            self.send_ms_test_button.state(["disabled"])

        def _worker():
            try:
                cfg = {"ms_token": {"ms_email_address": ms_email}}
                msg = EmailMessage()
                msg["To"] = ms_email
                msg["Subject"] = "MS Auth Test"
                msg.set_content("Success")

                send_email_via_graph(
                    cfg,
                    msg,
                    token_provider=self.msal_token_provider,
                    interactive=True,
                    secure_config=getattr(self, "secure_config", None),
                )
                self.root.after(0, lambda: messagebox.showinfo("MS Auth", "Test email sent successfully."))
            except Exception as exc:
                self.root.after(0, lambda err=exc: self._show_error_with_copy("MS Auth", f"Could not send test email:\n{err}"))
            finally:
                self._ms_test_in_progress = False
                if getattr(self, "send_ms_test_button", None):
                    self.root.after(0, lambda: self.send_ms_test_button.state(["!disabled"]))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_error_with_copy(self, title: str, message: str) -> None:
        popup = tk.Toplevel(self.root)
        popup.title(title)
        popup.transient(self.root)
        popup.grab_set()

        frame = ttk.Frame(popup, padding=10)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=title, font=("TkDefaultFont", 12, "bold")).pack(anchor="w", pady=(0, 6))

        text = tk.Text(frame, height=6, width=60, wrap="word")
        text.insert("1.0", message)
        text.config(state="disabled")
        text.pack(fill="both", expand=True)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Copy Error", command=lambda: self._copy_text_to_clipboard(message)).pack(side="left")
        ttk.Button(buttons, text="Close", command=popup.destroy).pack(side="right")

    def _copy_text_to_clipboard(self, value: str) -> None:
        if not value:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()
