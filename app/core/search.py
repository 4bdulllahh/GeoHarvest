"""A search: what the user asked for, which queries it becomes, and the leads it saved.

Options are a plain dict stored as JSON on the ``searches`` row, so a stopped
search can be resumed with exactly the settings it started with.
"""
from __future__ import annotations

import json

from app.core import db, geo

DEFAULT_OPTIONS = {
    "niches": [],             # "dentist", "real estate agency"...
    "country": "",
    "cities": [],             # empty: the country's biggest `city_count` cities
    "city_count": 10,
    "company_age": "any",     # any, startup, established (estimated, see enrich.py)
    "min_rating": 0.0,
    "min_reviews": 0,
    "require_website": False,
    "require_phone": False,
    "skip_closed": True,
    "skip_known": False,      # leave out businesses found by an earlier search
    "max_results": 0,         # 0: no limit
    "find_emails": True,      # visit websites for emails and social links
    "smart": False,           # AI check (milestone 5)
}


def options_with_defaults(options: dict) -> dict:
    return {**DEFAULT_OPTIONS, **options}


def places_for(options: dict) -> list[str]:
    """The places to search: the chosen cities, else the country's biggest ones."""
    country = options["country"]
    chosen = [c.strip() for c in options["cities"] if c.strip()]
    if not chosen and country:
        chosen = geo.cities(country)[: max(1, int(options["city_count"]))]
    if not chosen:
        return [country] if country else []
    return [f"{city}, {country}" if country else city for city in chosen]


def build_queries(options: dict) -> list[str]:
    options = options_with_defaults(options)
    niches = [n.strip() for n in options["niches"] if n.strip()]
    return [f"{niche} in {place}" for place in places_for(options) for niche in niches]


def title(options: dict) -> str:
    options = options_with_defaults(options)
    niches = ", ".join(n.strip() for n in options["niches"] if n.strip())
    cities = [c for c in options["cities"] if c.strip()]
    if cities:
        where = cities[0] if len(cities) == 1 else f"{len(cities)} cities"
        where += f", {options['country']}" if options["country"] else ""
    else:
        where = f"{options['country']} ({options['city_count']} biggest cities)"
    return f"{niches} in {where}"


def passes(lead: dict, options: dict) -> bool:
    """The filters that can be decided from Google's data alone."""
    if options["country"]:
        code = geo.country_code(options["country"])
        # Ambiguous city names ("Hyderabad", "Victoria") can pull in another country
        if code and lead.get("country_code") and lead["country_code"] != code:
            return False
    if options["skip_closed"] and lead.get("status") != "Open":
        return False
    if (lead.get("rating") or 0) < float(options["min_rating"] or 0):
        return False
    if (lead.get("reviews") or 0) < int(options["min_reviews"] or 0):
        return False
    if options["require_website"] and not lead.get("website"):
        return False
    if options["require_phone"] and not lead.get("phone"):
        return False
    return True


# --- storage ----------------------------------------------------------------
def create(options: dict) -> int:
    options = options_with_defaults(options)
    stamp = db.now()
    return db.execute(
        "INSERT INTO searches(created, updated, title, options, status) VALUES(?, ?, ?, ?, ?)",
        (stamp, stamp, title(options), json.dumps(options), "running"))


def get(search_id: int) -> dict | None:
    row = db.query_one("SELECT * FROM searches WHERE id = ?", (search_id,))
    if row is None:
        return None
    return {**dict(row), "options": options_with_defaults(json.loads(row["options"])),
            "progress": json.loads(row["progress"] or "{}")}


def set_status(search_id: int, status: str) -> None:
    db.execute("UPDATE searches SET status = ?, updated = ? WHERE id = ?",
               (status, db.now(), search_id))


def mark_query_done(search_id: int, query: str) -> None:
    progress = get(search_id)["progress"]
    done = progress.setdefault("done", [])
    if query not in done:
        done.append(query)
    db.execute("UPDATE searches SET progress = ?, updated = ? WHERE id = ?",
               (json.dumps(progress), db.now(), search_id))


def save_leads(search_id: int, leads: list[dict], skip_known: bool = False) -> list[dict]:
    """Store new leads; return only the ones that were actually new to this search."""
    saved = []
    conn = db.connect()
    stamp = db.now()
    for lead in leads:
        if skip_known and conn.execute(
                "SELECT 1 FROM leads WHERE place_id = ? AND search_id != ?",
                (lead["place_id"], search_id)).fetchone():
            continue
        cursor = conn.execute(
            "INSERT OR IGNORE INTO leads(search_id, place_id, created, data) VALUES(?, ?, ?, ?)",
            (search_id, lead["place_id"], stamp, json.dumps(lead, ensure_ascii=False)))
        if cursor.rowcount:
            saved.append(lead)
    conn.commit()
    return saved


def update_lead(search_id: int, place_id: str, fields: dict) -> None:
    """Merge extra fields (emails, AI score...) into a saved lead."""
    conn = db.connect()
    row = conn.execute("SELECT data FROM leads WHERE search_id = ? AND place_id = ?",
                       (search_id, place_id)).fetchone()
    if row is None:
        return
    data = {**json.loads(row["data"]), **fields}
    conn.execute("UPDATE leads SET data = ? WHERE search_id = ? AND place_id = ?",
                 (json.dumps(data, ensure_ascii=False), search_id, place_id))
    conn.commit()


def leads(search_id: int) -> list[dict]:
    return [json.loads(r["data"]) for r in
            db.query("SELECT data FROM leads WHERE search_id = ? ORDER BY id", (search_id,))]


def count(search_id: int) -> int:
    return db.query_one("SELECT COUNT(*) AS n FROM leads WHERE search_id = ?",
                        (search_id,))["n"]


def all_searches() -> list[dict]:
    """Newest first, with how many leads each one saved."""
    rows = db.query(
        "SELECT s.id, s.title, s.status, s.created, s.updated, COUNT(l.id) AS leads "
        "FROM searches s LEFT JOIN leads l ON l.search_id = s.id GROUP BY s.id ORDER BY s.id DESC")
    return [dict(row) for row in rows]


def all_leads() -> list[dict]:
    """Every lead from every search, each business once (its most recent copy)."""
    latest: dict[str, dict] = {}
    for row in db.query("SELECT place_id, data FROM leads ORDER BY id"):
        latest[row["place_id"]] = json.loads(row["data"])
    return list(latest.values())


def delete(search_id: int) -> None:
    db.execute("DELETE FROM leads WHERE search_id = ?", (search_id,))
    db.execute("DELETE FROM searches WHERE id = ?", (search_id,))
