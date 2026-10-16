"""SQLite storage: settings, searches and the leads each search found.

A lead is stored as one JSON document (``data``) rather than a column per field.
The scraper, the website enrichment and the AI check each add their own keys
over time, and the export reads whatever is there, so a new field never needs a
database migration.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from app import config

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS searches (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    created   TEXT NOT NULL,
    updated   TEXT NOT NULL,
    title     TEXT NOT NULL,
    options   TEXT NOT NULL,          -- JSON: niche, country, cities, filters, mode...
    status    TEXT NOT NULL,          -- running, stopped, done, failed
    progress  TEXT NOT NULL DEFAULT '{}'  -- JSON: which queries are finished, for resume
);
CREATE TABLE IF NOT EXISTS leads (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
    place_id  TEXT NOT NULL,
    created   TEXT NOT NULL,
    data      TEXT NOT NULL,          -- JSON: every field we know about the business
    UNIQUE (search_id, place_id)
);
CREATE INDEX IF NOT EXISTS leads_search ON leads(search_id);
CREATE INDEX IF NOT EXISTS leads_place ON leads(place_id);
"""

_local = threading.local()
_db_path: Path | None = None


def init(db_path: Path | None = None) -> None:
    global _db_path
    config.ensure_dirs()
    _db_path = Path(db_path) if db_path else config.DB_PATH
    conn = connect()
    conn.executescript(_SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def connect() -> sqlite3.Connection:
    """One connection per thread; scraper workers and the UI each get their own."""
    conn = getattr(_local, "conn", None)
    if conn is not None and getattr(_local, "path", None) == _db_path:
        return conn
    if _db_path is None:
        raise RuntimeError("db.init() must be called before db.connect()")
    conn = sqlite3.connect(str(_db_path), timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    _local.conn = conn
    _local.path = _db_path
    return conn


def close() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def query(sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    return connect().execute(sql, params).fetchall()


def query_one(sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    return connect().execute(sql, params).fetchone()


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    conn = connect()
    cursor = conn.execute(sql, params)
    conn.commit()
    return cursor.lastrowid


def execute_many(sql: str, rows: Iterable[Sequence[Any]]) -> None:
    conn = connect()
    conn.executemany(sql, rows)
    conn.commit()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --- settings ---------------------------------------------------------------
def get_setting(key: str, default: Any = None) -> Any:
    row = query_one("SELECT value FROM settings WHERE key = ?", (key,))
    if row is None or row["value"] is None:
        return default
    try:
        return json.loads(row["value"])
    except ValueError:
        return row["value"]


def set_setting(key: str, value: Any) -> None:
    execute("INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, json.dumps(value)))


def set_setting_soft(key: str, value: Any) -> bool:
    """Save a convenience setting; a busy database is not worth an error."""
    try:
        set_setting(key, value)
        return True
    except sqlite3.OperationalError:
        return False
