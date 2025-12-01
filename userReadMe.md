# Invoice Mailer User Guide

## Overview
- **Settings:** Configure folder paths, SMTP credentials, and choose whether the app runs in `Active` (real email) or `Test` (dry-run) mode.
- **Email Settings:** Define the email subject/body templates, sender identity, report recipients, and the billing month/year the run should target.
- **Scan:** Update the internal client database from your client list and scan the invoice/SOA folders for matching documents for the selected period.
- **Zip:** Package each client’s invoices and SOA files into ZIPs ready for emailing; shows what will be sent.
- **Send & Logs:** Send the prepared ZIPs by email (or simulate when in Test mode) and display progress and logs.

## How to Use the Program
1) Locate the packaged app `InvoiceMailer`.
2) The GUI opens on double-click.
3) In **Settings**, fill in folders/SMTP and pick `Test` while you validate.
4) In **Email Settings**, set templates plus month/year for the billing period; click **Save Email Settings**.
5) Run **Scan** to confirm the app finds the right invoices/SOAs and to refresh the change report.
6) Run **Zip** to generate the ZIP files and review the preview table.
7) Switch to **Active** only when ready to email; in **Send & Logs**, click **Start Email Send** and watch the log/progress.

## Tab Details

### Settings Tab (fields)
- **Invoice Folder:** Folder containing invoice PDFs; required for scanning/zipping/sending.
- **SOA Folder:** Folder containing statements of account; required to pair with invoices.
- **Client List File:** Excel/CSV file that defines clients; used to refresh the internal DB.
- **ZIP Output Folder:** Where generated ZIPs are saved; leave blank to store alongside source files.
- **Mode (Active/Test):**  
  - `Test`: Dry run; ZIPs still generate, but email sending is simulated.  
  - `Active`: Real email delivery using your SMTP server. The **Send & Logs** banner shows the current mode in red (Active) or blue (Test).
- **SMTP Host/Port/Username/Password/From Address/Use TLS:** Mail server settings used when sending in **Active** mode; still required so Test runs can validate connectivity/configuration.
- **Save Settings:** Persists the above values and updates the “Current Settings” summary so you can double-check what’s stored.

### Email Settings Tab (fields)
- **Subject Template:** Email subject line template for outgoing invoices.
- **Body Template:** Multiline email body; supports the text sent with each ZIP.
- **Sender Name:** Friendly display name for the From header.
- **Reporter Emails (comma separated):** Addresses to receive run reports/notifications.
- **Month / Year:** Billing period to use when scanning, zipping, and sending; both are required before scan/zip/send actions.
- **Save Email Settings:** Saves the email-related fields and updates the “Current Email Settings” summary.

### Scan Tab
- **Start Scan:** Refreshes the client database from the client list file, then scans the invoice and SOA folders for the chosen month/year.
- **Change Report:** Shows any DB updates performed during the scan (or notes if none were needed).
- **Results Table:** Lists each matched invoice with client aggregate, head office, customer number, ship, invoice number/date, and the matched invoice/SOA filenames.
- Use this tab to verify the period selection and file matches before zipping/sending.

### Zip Tab
- **Generate ZIP:** Runs the same scan logic, then packages per-client ZIP files to the configured output folder.
- **Status Message:** Reports change-log info from the DB refresh or confirms completion.
- **Preview Table:** Displays each client, the period string, and the ZIP filename so you can validate what will be emailed.
- The resulting ZIP list is reused by the Send tab; rerun here if you change inputs or month/year.

### Send & Logs Tab
- **Mode Banner:** Shows whether the app is in `Active - Emails will send` (red) or `Test - Dry run (no emails sent)` (blue). This reflects the Mode from the Settings tab.
- **Start Email Send:** Sends emails with the prepared ZIPs. In Test mode it simulates delivery without contacting real recipients; in Active mode it uses the SMTP settings to deliver.
- **Clear Text Screen:** Clears the log output and progress bar.
- **Progress + Log:** Progress bar shows overall completion; the log records start/end messages, change reports, and email results. Errors will also appear in a pop-up dialog.
- If you have not generated ZIPs yet, this tab will scan and build them on the fly using your current settings.
