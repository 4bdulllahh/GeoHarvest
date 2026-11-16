"""crash.log in the data folder's logs: the full details of errors the user only sees a
short message for. Testers attach it to their reports."""
from __future__ import annotations

from datetime import datetime

from app import config

MAX_BYTES = 1_000_000  # past this the older half is dropped, so the file never fills a disk


def record(details: str) -> None:
    """Add an error to crash.log with the time. Never raises: this is called while another
    error is being handled, and a log that can't be written has nowhere left to report to."""
    try:
        config.ensure_dirs()
        path = config.LOGS_DIR / "crash.log"
        if path.exists() and path.stat().st_size > MAX_BYTES:
            path.write_bytes(path.read_bytes()[-MAX_BYTES // 2:])
        with path.open("a", encoding="utf-8") as log:
            log.write(f"\n--- {datetime.now().isoformat(timespec='seconds')} ---\n{details}\n")
    except Exception:  # noqa: BLE001, S110
        pass
