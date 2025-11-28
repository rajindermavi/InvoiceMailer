"""
Local SMTP debug server for development/testing.

- Listens on localhost:1025 (no TLS, no auth).
- Prints incoming messages to stdout.
- Saves each raw message to tmp/dev_emails/*.eml for inspection.
"""

import time
from datetime import datetime
from pathlib import Path

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import Envelope


class SavingHandler:
    """Debug handler that writes messages to disk."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def handle_DATA(
        self,
        server,
        session,
        envelope: Envelope,
    ):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        file_path = self.output_dir / f"message_{timestamp}.eml"

        # envelope.content is bytes; fall back to original_content if present.
        raw = envelope.original_content or envelope.content
        if isinstance(raw, str):
            raw = raw.encode("utf-8", "replace")

        file_path.write_bytes(raw)
        print(
            f"[DEV SMTP] From: {envelope.mail_from} -> {envelope.rcpt_tos} | "
            f"saved to {file_path}"
        )
        return "250 Message accepted for delivery"


def main() -> None:
    host = "127.0.0.1"
    port = 1025
    out_dir = Path(__file__).parent / "tmp" / "dev_emails"

    handler = SavingHandler(output_dir=out_dir)
    controller = Controller(handler, hostname=host, port=port)

    print(f"Starting debug SMTP server on {host}:{port}")
    print("Press Ctrl+C to stop.")
    controller.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping debug SMTP server.")
    finally:
        controller.stop()
        # Ensure the underlying loop shuts down cleanly.
        if controller.loop and controller.loop.is_running():
            controller.loop.call_soon_threadsafe(controller.loop.stop)


if __name__ == "__main__":
    main()
