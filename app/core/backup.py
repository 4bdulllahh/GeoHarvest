"""Backups of the database: by hand from Settings, and once a week by themselves.

A backup is GeoHarvest's SQLite database copied with SQLite's own backup API, so
it is consistent even while the app is open. The AI key and proxies are not in
it: they live in the encrypted secrets file, which only this Windows account can
read, so they would be no use on another computer anyway.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from app import config
from app.core import db

SUFFIX = ".ghbackup"
AUTO_NAME = "GeoHarvest auto backup"
AUTO_KEEP = 4
AUTO_EVERY = timedelta(days=7)


def folder() -> Path:
    return config.DATA_DIR / "backups"


def write_backup(target: str | Path) -> Path:
    destination = sqlite3.connect(str(target))
    try:
        with destination:
            db.connect().backup(destination)
    finally:
        destination.close()
    return Path(target)


def is_backup(source: str | Path) -> bool:
    try:
        connection = sqlite3.connect(f"file:{Path(source).as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        connection.execute("SELECT 1 FROM searches LIMIT 1")
        connection.execute("SELECT 1 FROM leads LIMIT 1")
        return True
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def restore_backup(source: str | Path) -> Path:
    """Replace the live database with a backup; what was there is kept as a backup first."""
    folder().mkdir(parents=True, exist_ok=True)
    safety = write_backup(folder() / f"Before restoring {datetime.now():%Y-%m-%d %H%M}{SUFFIX}")
    backup = sqlite3.connect(f"file:{Path(source).as_posix()}?mode=ro", uri=True)
    try:
        with db.connect() as live:
            backup.backup(live)
    finally:
        backup.close()
    return safety


def default_name() -> str:
    return f"GeoHarvest backup {datetime.now():%Y-%m-%d}{SUFFIX}"


def last_backup() -> str:
    """When the newest backup was made, by hand or by itself; "" if never."""
    return max(db.get_setting("last_backup", ""), db.get_setting("last_auto_backup", ""))


def auto_backup(now: datetime | None = None) -> Path | None:
    """Once a week, a backup in the data folder; only the newest AUTO_KEEP are kept."""
    if not db.get_setting("auto_backup", True):
        return None
    now = now or datetime.now()
    last = db.get_setting("last_auto_backup", "")
    if last and now - datetime.fromisoformat(last) < AUTO_EVERY:
        return None
    folder().mkdir(parents=True, exist_ok=True)
    path = write_backup(folder() / f"{AUTO_NAME} {now:%Y-%m-%d}{SUFFIX}")
    db.set_setting("last_auto_backup", now.isoformat(timespec="seconds"))
    for old in sorted(folder().glob(f"{AUTO_NAME} *{SUFFIX}"))[:-AUTO_KEEP]:
        old.unlink(missing_ok=True)
    return path
