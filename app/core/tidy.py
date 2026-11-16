"""Freeing disk space. Most of the database is the stored details of businesses a search
left out (about 1.5 KB each, tens of thousands in a big search). For a finished search
nothing reads those details again, so "Free up space" in Settings cuts them down.

What is always kept (see M13 in docs/handover/audit-2026-11.md):
  * every row and its reason, so a business is never added twice and the "left out" counts
    stay right;
  * each row's place, map position and query, which digging deeper reads;
  * whole rows of leads and of businesses that fit;
  * whole rows deleted by the user or found by an earlier search;
  * whole rows left out for company age, which "Any age" can still bring back;
  * everything in a search that is not finished (it can still be resumed or widened).
"""
from __future__ import annotations

from app.core import db
from app.core import search as searches

_NOT_TRIMMED = "json_extract(data, '$.trimmed') IS NULL"


def _spare() -> list[tuple[int, str]]:
    """(search id, reason) of the left-out businesses whose details can go."""
    rows = db.query(
        "SELECT DISTINCT c.search_id AS search_id, c.dropped AS reason FROM candidates c "
        "JOIN searches s ON s.id = c.search_id "
        "WHERE s.status = 'done' AND c.dropped IS NOT NULL")
    return [(r["search_id"], r["reason"]) for r in rows
            if r["reason"] not in (searches.KNOWN, searches.REMOVED)
            and not searches.is_age_reason(r["reason"])]


def spare_bytes() -> int:
    """About how much "Free up space" would free. Reads every left-out row, so call it
    from a worker, not the UI thread."""
    total = 0
    for pair in _spare():
        row = db.query_one(
            "SELECT COALESCE(SUM(length(data)), 0) AS size FROM candidates "
            f"WHERE search_id = ? AND dropped = ? AND {_NOT_TRIMMED}", pair)
        total += row["size"]
    return total


def free_space() -> int:
    """Cut the spare details down and shrink the database file. Returns the bytes freed on
    disk. Slow (it rewrites the file): call it from a worker, with no search running."""
    before = db.file_size()
    conn = db.connect()
    conn.executemany(
        "UPDATE candidates SET data = json_object('place_id', place_id, "
        "'query', json_extract(data, '$.query'), 'latitude', json_extract(data, '$.latitude'), "
        "'longitude', json_extract(data, '$.longitude'), 'trimmed', 1) "
        f"WHERE search_id = ? AND dropped = ? AND {_NOT_TRIMMED}", _spare())
    conn.commit()
    conn.execute("VACUUM")  # hands the freed pages back to Windows
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return max(0, before - db.file_size())
