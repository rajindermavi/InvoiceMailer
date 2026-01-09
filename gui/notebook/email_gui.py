from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from datetime import datetime

from gui.utility import apply_settings_to_vars


class _TextAdapter:
    """Minimal adapter to let apply/settings helpers work with a Text widget."""

    def __init__(self, widget: tk.Text):
        self.widget = widget

    def set(self, value: str) -> None:
        self.widget.delete("1.0", "end")
        self.widget.insert("1.0", value or "")

    def get(self) -> str:
        return self.widget.get("1.0", "end").strip()


class EmailSettingsTab:
    """
    Mixin for the Email Settings tab.
    Expects the consumer to define:
    - self.tab_email (ttk.Frame)
    - self.settings (dict)
    - self.save_settings (callable)
    """

    def build_email_tab(self):
        container = ttk.Frame(self.tab_email)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        frame = ttk.LabelFrame(container, text="Email Settings")
        frame.pack(fill="x", padx=5, pady=(0, 10))

        # Subject
        ttk.Label(frame, text="Subject Template:").grid(row=0, column=0, sticky="w")
        self.subject_template_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.subject_template_var, width=60).grid(row=0, column=1, padx=5, pady=2, sticky="w")

        # Body (multiline)
        ttk.Label(frame, text="Body Template:").grid(row=1, column=0, sticky="nw")
        self.body_template_text = tk.Text(frame, width=60, height=5, wrap="word")
        self.body_template_text.grid(row=1, column=1, padx=5, pady=2, sticky="w")

        # Sender name
        ttk.Label(frame, text="Sender Name:").grid(row=2, column=0, sticky="w")
        self.sender_name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.sender_name_var, width=40).grid(row=2, column=1, padx=5, pady=2, sticky="w")

        # Reporter emails
        ttk.Label(frame, text="Reporter Emails (comma separated):").grid(row=3, column=0, sticky="w")
        self.reporter_emails_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.reporter_emails_var, width=60).grid(row=3, column=1, padx=5, pady=2, sticky="w")

        # Month and Year dropdowns
        ttk.Label(frame, text="Month:").grid(row=4, column=0, sticky="w")
        self.email_month_var = tk.StringVar()
        ttk.Combobox(frame, textvariable=self.email_month_var, values=[str(i) for i in range(1, 13)], width=8).grid(row=4, column=1, sticky="w", padx=5, pady=2)

        current_year = datetime.now().year
        year_options = [str(y) for y in range(current_year - 7, current_year + 3)]
        ttk.Label(frame, text="Year:").grid(row=5, column=0, sticky="w")
        self.email_year_var = tk.StringVar()
        ttk.Combobox(frame, textvariable=self.email_year_var, values=year_options, width=8).grid(row=5, column=1, sticky="w", padx=5, pady=2)

        body_template_adapter = _TextAdapter(self.body_template_text)
        self._email_settings_vars = {
            "subject_template": self.subject_template_var,
            "body_template": body_template_adapter,
            "sender_name": self.sender_name_var,
            "reporter_emails": self.reporter_emails_var,
            "email_month": self.email_month_var,
            "email_year": self.email_year_var,
        }
        apply_settings_to_vars(self._email_settings_vars, self.settings)

        ttk.Button(container, text="Save Email Settings", command=self.save_settings).pack(fill="x", padx=5, pady=(0, 10))

        current_frame = ttk.LabelFrame(container, text="Current Email Settings")
        current_frame.pack(fill="x", padx=5, pady=(0, 5))
        current_frame.columnconfigure(0, weight=1)
        ttk.Style().configure(
            "EmailWarning.TLabel",
            foreground="gray40",
            font=("TkDefaultFont", 9, "italic"),
        )

        self.subject_label_var = tk.StringVar(value="Subject Template: (not saved)")
        self.sender_label_var = tk.StringVar(value="Sender Name: (not saved)")
        self.reporters_label_var = tk.StringVar(value="Reporter Emails: (not saved)")
        self.body_label_var = tk.StringVar(value="Body Template: (not saved)")
        self.month_label_var = tk.StringVar(value="Month: (not saved)")
        self.year_label_var = tk.StringVar(value="Year: (not saved)")

        ttk.Label(current_frame, textvariable=self.subject_label_var).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(current_frame, textvariable=self.sender_label_var).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Label(current_frame, textvariable=self.reporters_label_var).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Label(current_frame, textvariable=self.month_label_var).grid(row=3, column=0, sticky="w", pady=2)
        ttk.Label(current_frame, textvariable=self.year_label_var).grid(row=4, column=0, sticky="w", pady=2)
        ttk.Label(
            current_frame,
            text="Scan will retrieve selected month and following month.",
            style="EmailWarning.TLabel",
        ).grid(row=5, column=0, sticky="w", pady=(2, 0))
        ttk.Label(current_frame, textvariable=self.body_label_var, wraplength=700, justify="left").grid(row=6, column=0, sticky="w", pady=2)

        self.update_email_settings_display()

    def update_email_settings_display(self):
        body = self.settings.get("body_template", "") or "(empty)"
        self.subject_label_var.set(f"Subject Template: {self.settings.get('subject_template') or '(empty)'}")
        self.sender_label_var.set(f"Sender Name: {self.settings.get('sender_name') or '(empty)'}")
        self.reporters_label_var.set(f"Reporter Emails: {self.settings.get('reporter_emails') or '(empty)'}")
        self.body_label_var.set(f"Body Template: {body}")
        month = self.settings.get("email_month") or "(empty)"
        year = self.settings.get("email_year") or "(empty)"
        self.month_label_var.set(f"Month: {month}")
        self.year_label_var.set(f"Year: {year}")
