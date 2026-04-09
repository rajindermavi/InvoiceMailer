from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from src.gui.utility import apply_settings_to_vars, settings_from_vars


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

        self._auth_frame_pack_opts = {"fill": "x", "padx": 5, "pady": (0, 10)}

        self.ms_email_address_var = tk.StringVar()
        self.ms_authority_var = tk.StringVar(value="organizations")
        self.ms_client_id_var = tk.StringVar()

        self._settings_vars = {
            "invoice_folder": self.invoice_folder_var,
            "soa_folder": self.soa_folder_var,
            "client_file": self.client_file_var,
            "output_folder": self.output_folder_var,
            "aggregate_by": self.aggregate_by_var,
            "mode": self.mode_var,
            "ms_email_address": self.ms_email_address_var,
            "ms_authority": self.ms_authority_var,
            "ms_client_id": self.ms_client_id_var,
        }
        apply_settings_to_vars(self._settings_vars, self.settings)
        self.ms_authority_var.trace_add("write", self._handle_ms_authority_change)

        self.auth_content = ttk.Frame(container)
        self.auth_content.pack(**self._auth_frame_pack_opts)

        self.ms_auth_frame = ttk.LabelFrame(self.auth_content, text="MS Auth")
        ttk.Label(self.ms_auth_frame, text="Account Type:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        authority_frame = ttk.Frame(self.ms_auth_frame)
        authority_frame.grid(row=2, column=1, padx=5, pady=2, sticky="w")
        ttk.Radiobutton(
            authority_frame,
            text="Work/School (organizations)",
            variable=self.ms_authority_var,
            value="organizations",
            command=self._handle_ms_authority_change,
        ).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            authority_frame,
            text="Personal Outlook (consumers)",
            variable=self.ms_authority_var,
            value="consumers",
            command=self._handle_ms_authority_change,
        ).pack(side="left")
        ttk.Label(self.ms_auth_frame, text="MS Email Address:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Entry(self.ms_auth_frame, textvariable=self.ms_email_address_var, width=40).grid(row=1, column=1, padx=5, pady=2, sticky="w")
        ttk.Label(self.ms_auth_frame, text="Azure App (Client) ID:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        ttk.Entry(self.ms_auth_frame, textvariable=self.ms_client_id_var, width=40).grid(row=3, column=1, padx=5, pady=2, sticky="w")

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
        self.ms_email_address_label_var = tk.StringVar(value="MS Email Address: (not saved)")
        self.ms_authority_label_var = tk.StringVar(value="MS Authority: (not saved)")
        self.ms_client_id_label_var = tk.StringVar(value="Azure Client ID: (not saved)")

        cfg_summary = ttk.Frame(current_frame)
        cfg_summary.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ttk.Label(cfg_summary, textvariable=self.invoice_folder_label_var).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.soa_folder_label_var).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.client_file_label_var).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.output_folder_label_var).grid(row=3, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.aggregate_by_label_var).grid(row=4, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.mode_label_var).grid(row=5, column=0, sticky="w", pady=2)

        self.ms_summary = ttk.Frame(current_frame)
        self.ms_summary.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ttk.Label(self.ms_summary, textvariable=self.ms_email_address_label_var).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(self.ms_summary, textvariable=self.ms_authority_label_var).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Label(self.ms_summary, textvariable=self.ms_client_id_label_var).grid(row=2, column=0, sticky="w", pady=2)

        self.update_current_settings_display()

    def _refresh_auth_frames(self, *_):
        self.ms_auth_frame.pack(fill="x")
        if hasattr(self, "ms_summary"):
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
        self.ms_email_address_label_var.set(f"MS Email Address: {self.settings.get('ms_email_address') or '(empty)'}")
        self.ms_authority_label_var.set(f"MS Authority: {self.settings.get('ms_authority') or '(empty)'}")
        self.ms_client_id_label_var.set(f"Azure Client ID: {self.settings.get('ms_client_id') or '(empty)'}")
        self._refresh_current_summary_frames()

    def _refresh_current_summary_frames(self):
        self.ms_summary.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

    def _handle_ms_authority_change(self, *_):
        value = (self.ms_authority_var.get() or "organizations").strip() or "organizations"
        if hasattr(self, "settings"):
            self.settings["ms_authority"] = value
        self.update_current_settings_display()

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
