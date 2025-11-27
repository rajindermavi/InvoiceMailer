# Local SMTP Test Server

Run a local SMTP debug server so you can exercise the email sender without touching a real mail relay:

1) Install dev deps if needed: `pip install -r requirements.txt` (includes `aiosmtpd` for the server).
2) Start the server: `python dev_smtp_server.py` (listens on `localhost:1025`, no TLS/auth). Messages print to stdout and save under `tmp/dev_emails/`.
2) Point your dev config to it in `config.dev.ini` under `[smtp]`:
   - `host = localhost`
   - `port = 1025`
   - `use_tls = false`
   - `username =` (leave blank)
   - `password =` (leave blank)
   - `from_address = you@example.com`
3) Run your mailer (set `dry_run=False`) to send. Inspect the `.eml` files in `tmp/dev_emails/` or read the console output to verify headers and attachments.

# Storing SMTP Password Securely (Keyring)

Keep SMTP credentials out of config files by using the OS keyring:

- Install dependencies: `pip install -r requirements.txt` (includes `keyring`).
- First run: when you start the app, call `get_or_prompt_secret("smtp_password", username="<your_smtp_username>")` to fetch the password from the keyring; you’ll be prompted once if it’s missing and it will be stored securely.
- Build `SMTPConfig` using the returned password instead of reading a plaintext `password` from `config.dev.ini`.
- To clear the stored password: `delete_secret("smtp_password", username="<your_smtp_username>")`.
