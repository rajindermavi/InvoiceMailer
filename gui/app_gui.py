import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading

from backend.workflow import run_workflow

class InvoiceMailerGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("Invoice Mailer")
        self.root.geometry("900x650")

        # -----------------------------
        # Notebook (Tabs)
        # -----------------------------
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)

        self.tab_settings = ttk.Frame(self.notebook)
        self.tab_scan = ttk.Frame(self.notebook)
        self.tab_preview = ttk.Frame(self.notebook)
        self.tab_send = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_settings, text="Settings")
        self.notebook.add(self.tab_scan, text="Scan")
        self.notebook.add(self.tab_preview, text="Preview")
        self.notebook.add(self.tab_send, text="Send & Logs")

        # -----------------------------
        # Build UI for each tab
        # -----------------------------
        self.build_settings_tab()
        self.build_scan_tab()
        self.build_preview_tab()
        self.build_send_tab()

    # ------------------------------------------------------------
    # SETTINGS TAB
    # ------------------------------------------------------------
    def build_settings_tab(self):
        frame = ttk.LabelFrame(self.tab_settings, text="Configuration")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Invoice folder
        ttk.Label(frame, text="Invoice Folder:").grid(row=0, column=0, sticky="w")
        self.invoice_folder_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.invoice_folder_var, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(frame, text="Browse", command=self.pick_invoice_folder).grid(row=0, column=2, padx=5)

        # Output ZIP folder
        ttk.Label(frame, text="ZIP Output Folder:").grid(row=1, column=0, sticky="w")
        self.output_folder_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.output_folder_var, width=50).grid(row=1, column=1, padx=5)
        ttk.Button(frame, text="Browse", command=self.pick_output_folder).grid(row=1, column=2, padx=5)

        # Client list
        ttk.Label(frame, text="Client List File:").grid(row=2, column=0, sticky="w")
        self.client_file_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.client_file_var, width=50).grid(row=2, column=1, padx=5)
        ttk.Button(frame, text="Browse", command=self.pick_client_file).grid(row=2, column=2, padx=5)

        # Mode (dev/prod)
        ttk.Label(frame, text="Mode:").grid(row=3, column=0, sticky="w")
        self.mode_var = tk.StringVar(value="prod")
        ttk.Combobox(frame, textvariable=self.mode_var, values=["dev", "prod"], width=10).grid(row=3, column=1, sticky="w")

        # Save config button
        ttk.Button(frame, text="Save Settings", command=self.save_settings).grid(row=4, column=0, columnspan=3, pady=20)

    # Folder pickers
    def pick_invoice_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.invoice_folder_var.set(folder)

    def pick_output_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_folder_var.set(folder)

    def pick_client_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Excel/CSV", "*.xlsx *.csv"), ("All files", "*.*")])
        if file_path:
            self.client_file_var.set(file_path)

    def save_settings(self):
        messagebox.showinfo("Saved", "Settings saved successfully!")

    # ------------------------------------------------------------
    # SCAN TAB
    # ------------------------------------------------------------
    def build_scan_tab(self):
        frame = ttk.LabelFrame(self.tab_scan, text="Scan for Invoices")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Button(frame, text="Start Scan", command=self.start_scan).pack(pady=10)

        # Treeview for scan results
        self.scan_table = ttk.Treeview(frame, columns=("file", "client", "status"), show="headings")
        self.scan_table.heading("file", text="Invoice File")
        self.scan_table.heading("client", text="Client")
        self.scan_table.heading("status", text="Status")
        self.scan_table.pack(fill="both", expand=True, pady=10)

    def start_scan(self):
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        # this is where you call backend.scan()
        # placeholder example:
        demo_rows = [
            ("INV001_Jan.pdf", "Client A", "Matched"),
            ("INV002_Jan.pdf", "Client B", "Matched"),
            ("weirdfile.tmp", "Unknown", "Unmatched"),
        ]
        self.update_scan_table(demo_rows)

    def update_scan_table(self, rows):
        # Clear table
        for row in self.scan_table.get_children():
            self.scan_table.delete(row)
        # Insert new
        for r in rows:
            self.scan_table.insert("", "end", values=r)

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
        results = run_workflow()
        self.log_msg("Workflow finished.")

def start_gui():
    root = tk.Tk()
    InvoiceMailerGUI(root)
    root.mainloop()