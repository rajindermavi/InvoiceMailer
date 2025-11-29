from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog

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

        # Aggregate by
        ttk.Label(frame, text="Aggregate By:").grid(row=4, column=0, sticky="w")
        self.aggregate_by_var = tk.StringVar(value="head_office")
        ttk.Combobox(
            frame,
            textvariable=self.aggregate_by_var,
            values=["head_office", "customer_number"],
            width=18,
        ).grid(row=4, column=1, sticky="w")

        # Mode (dev/prod)
        ttk.Label(frame, text="Mode:").grid(row=5, column=0, sticky="w")
        self.mode_var = tk.StringVar(value="Active")
        ttk.Combobox(frame, textvariable=self.mode_var, values=["Active", "Test"], width=10).grid(row=5, column=1, sticky="w")

        smtp_frame = ttk.LabelFrame(container, text="SMTP")
        smtp_frame.pack(fill="x", padx=5, pady=(0, 10))

        self.smtp_host_var = tk.StringVar(value="smtp.gmail.com")
        self.smtp_port_var = tk.StringVar(value="587")
        self.smtp_username_var = tk.StringVar()
        self.smtp_password_var = tk.StringVar()
        self.smtp_from_var = tk.StringVar()
        self.smtp_use_tls_var = tk.BooleanVar(value=True)

        self._settings_vars = {
            "invoice_folder": self.invoice_folder_var,
            "soa_folder": self.soa_folder_var,
            "client_file": self.client_file_var,
            "output_folder": self.output_folder_var,
            "aggregate_by": self.aggregate_by_var,
            "mode": self.mode_var,
            "smtp_host": self.smtp_host_var,
            "smtp_port": self.smtp_port_var,
            "smtp_username": self.smtp_username_var,
            "smtp_password": self.smtp_password_var,
            "smtp_from": self.smtp_from_var,
            "smtp_use_tls": self.smtp_use_tls_var,
        }
        apply_settings_to_vars(self._settings_vars, self.settings)

        ttk.Label(smtp_frame, text="Host:").grid(row=0, column=0, sticky="w")
        ttk.Entry(smtp_frame, textvariable=self.smtp_host_var, width=40).grid(row=0, column=1, padx=5, sticky="w")

        ttk.Label(smtp_frame, text="Port:").grid(row=1, column=0, sticky="w")
        ttk.Entry(smtp_frame, textvariable=self.smtp_port_var, width=10).grid(row=1, column=1, padx=5, sticky="w")

        ttk.Label(smtp_frame, text="Username:").grid(row=2, column=0, sticky="w")
        ttk.Entry(smtp_frame, textvariable=self.smtp_username_var, width=40).grid(row=2, column=1, padx=5, sticky="w")

        ttk.Label(smtp_frame, text="Password:").grid(row=3, column=0, sticky="w")
        ttk.Entry(smtp_frame, textvariable=self.smtp_password_var, show="*", width=40).grid(row=3, column=1, padx=5, sticky="w")

        ttk.Label(smtp_frame, text="From Address:").grid(row=4, column=0, sticky="w")
        ttk.Entry(smtp_frame, textvariable=self.smtp_from_var, width=40).grid(row=4, column=1, padx=5, sticky="w")

        ttk.Checkbutton(smtp_frame, text="Use TLS", variable=self.smtp_use_tls_var).grid(row=5, column=0, columnspan=2, sticky="w")

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
        self.smtp_host_label_var = tk.StringVar(value="SMTP Host: (not saved)")
        self.smtp_port_label_var = tk.StringVar(value="SMTP Port: (not saved)")
        self.smtp_username_label_var = tk.StringVar(value="SMTP Username: (not saved)")
        self.smtp_password_label_var = tk.StringVar(value="SMTP Password: (not saved)")
        self.smtp_from_label_var = tk.StringVar(value="From Address: (not saved)")
        self.smtp_tls_label_var = tk.StringVar(value="Use TLS: (not saved)")

        cfg_summary = ttk.Frame(current_frame)
        cfg_summary.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ttk.Label(cfg_summary, textvariable=self.invoice_folder_label_var).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.soa_folder_label_var).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.client_file_label_var).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.output_folder_label_var).grid(row=3, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.aggregate_by_label_var).grid(row=4, column=0, sticky="w", pady=2)
        ttk.Label(cfg_summary, textvariable=self.mode_label_var).grid(row=5, column=0, sticky="w", pady=2)

        smtp_summary = ttk.Frame(current_frame)
        smtp_summary.grid(row=0, column=1, sticky="nsew")
        ttk.Label(smtp_summary, textvariable=self.smtp_host_label_var).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(smtp_summary, textvariable=self.smtp_port_label_var).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Label(smtp_summary, textvariable=self.smtp_username_label_var).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Label(smtp_summary, textvariable=self.smtp_password_label_var).grid(row=3, column=0, sticky="w", pady=2)
        ttk.Label(smtp_summary, textvariable=self.smtp_from_label_var).grid(row=4, column=0, sticky="w", pady=2)
        ttk.Label(smtp_summary, textvariable=self.smtp_tls_label_var).grid(row=5, column=0, sticky="w", pady=2)

        self.update_current_settings_display()

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
        self.settings = settings_from_vars(self._settings_vars)

        self.invoice_folder_label_var.set(f"Invoice Folder: {self.settings['invoice_folder'] or '(empty)'}")
        self.soa_folder_label_var.set(f"SOA Folder: {self.settings['soa_folder'] or '(empty)'}")
        self.output_folder_label_var.set(f"ZIP Output Folder: {self.settings['output_folder'] or '(empty)'}")
        self.client_file_label_var.set(f"Client List File: {self.settings['client_file'] or '(empty)'}")
        self.aggregate_by_label_var.set(f"Aggregate By: {self.settings['aggregate_by'].replace('_',' ').title() or '(empty)'}")
        self.mode_label_var.set(f"Mode: {self.settings['mode'] or '(empty)'}")
        self.smtp_host_label_var.set(f"SMTP Host: {self.settings['smtp_host'] or '(empty)'}")
        self.smtp_port_label_var.set(f"SMTP Port: {self.settings['smtp_port'] or '(empty)'}")
        self.smtp_username_label_var.set(f"SMTP Username: {self.settings['smtp_username'] or '(empty)'}")
        masked_pwd = "*" * len(self.settings['smtp_password']) if self.settings['smtp_password'] else "(empty)"
        self.smtp_password_label_var.set(f"SMTP Password: {masked_pwd}")
        self.smtp_from_label_var.set(f"From Address: {self.settings['smtp_from'] or '(empty)'}")
        self.smtp_tls_label_var.set(f"Use TLS: {'Yes' if self.settings['smtp_use_tls'] else 'No'}")
