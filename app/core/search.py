"""A search: what the user asked for, which queries it becomes, and the leads it saved.

Options are a plain dict stored as JSON on the ``searches`` row, so a stopped
search can be resumed with exactly the settings it started with.
"""
from __future__ import annotations

import json
import math

from app.core import db, geo, hours
from app.core.places import FIELDS, SERVICE_AREA

DEFAULT_OPTIONS = {
    "niches": [],             # "dentist", "real estate agency"...
    "where": "cities",        # cities (countries + ticked cities) or area (around one place)
    "area_place": "",         # "Dubai Marina": typed by the user...
    "area_km": 5,
    "area_lat": None,         # ...and found on the map when the search starts
    "area_lng": None,
    "countries": [],          # countries and/or regions ("European Union"), as typed
    "cities": [],             # "City, Country" as ticked; empty: each country's biggest
    "city_count": 10,
    "company_age": "any",     # any, startup, established (estimated, see enrich.py)
    "min_rating": 0.0,
    "min_reviews": 0,
    "max_rating": 0.0,        # 0: no maximum
    "max_reviews": -1,        # -1: no maximum (0 is a real choice: no reviews yet)
    "website": "any",         # any, yes (must have one), no (must not: leads for web designers)
    "require_phone": False,
    "require_address": False,  # leave out businesses that hide their address on Google
    "open_now": False,        # opening hours filters; leads without listed hours are left out
    "open_24h": False,
    "open_weekends": False,
    "open_at": False,         # open on open_day (0 = Monday) at open_time ("HH:MM")
    "open_day": 4,
    "open_time": "20:00",
    "skip_closed": True,
    "skip_known": True,       # leave out businesses found by an earlier search
    "max_results": 0,         # 0: no limit; else the best this many (see balanced)
    "find_emails": True,      # visit websites for emails and social links
    "find_owner": False,      # owner's name from the website and domain record, LinkedIn link
    "smart": False,           # score every lead with the user's AI
    "fields": [key for key, _ in FIELDS],  # columns to show and export; leads keep everything
}


def options_with_defaults(options: dict) -> dict:
    merged = {**DEFAULT_OPTIONS, **options}
    if merged.pop("country", None) and not options.get("countries"):  # saved before 0.1
        merged["countries"] = [options["country"]]
    if merged.pop("require_website", False) and "website" not in options:  # before 0.2.1
        merged["website"] = "yes"
    return merged


def places_for(options: dict) -> list[str]:
    """The places to search: the ticked cities, else each country's biggest `city_count`."""
    countries = geo.expand(options["countries"])
    chosen = [c.strip() for c in options["cities"] if c.strip()]
    if chosen:
        # Searches saved before the city checklist stored bare city names with one country
        return [c if "," in c or len(countries) != 1 else f"{c}, {countries[0]}" for c in chosen]
    count = max(1, int(options["city_count"]))
    places = []
    for country in countries:
        biggest = geo.cities(country)[:count]
        places += [f"{city}, {country}" for city in biggest] if biggest else [country]
    return places


def build_queries(options: dict) -> list[str]:
    """One query per business type and city, or per business type and map view of an area.

    Area queries end in "@lat,lng,camera" (see ``scraper.search``); before the place has
    been found on the map they still count right, for the plan shown on the form.
    """
    options = options_with_defaults(options)
    niches = [n.strip() for n in options["niches"] if n.strip()]
    if options["where"] == "area":
        place = options["area_place"].strip()
        cells = geo.radius_cells(options["area_lat"] or 0.0, options["area_lng"] or 0.0,
                                 float(options["area_km"])) if place else []
        return [f"{niche} near {place} @{lat},{lng},{camera}"
                for lat, lng, camera in cells for niche in niches]
    return [f"{niche} in {place}" for place in places_for(options) for niche in niches]


def title(options: dict) -> str:
    options = options_with_defaults(options)
    niches = ", ".join(n.strip() for n in options["niches"] if n.strip())
    if options["where"] == "area":
        return f"{niches} within {options['area_km']} km of {options['area_place'].strip()}"
    named = [geo.resolve(c) or c for c in options["countries"]]
    countries = geo.expand(options["countries"])
    cities = [c for c in options["cities"] if c.strip()]
    if cities:
        where = cities[0] if len(cities) == 1 else f"{len(cities)} cities"
        if len(cities) > 1 and countries:
            where += " in " + (", ".join(countries) if len(countries) <= 3
                               else f"{len(countries)} countries")
        elif len(cities) == 1 and "," not in cities[0] and len(countries) == 1:
            where += f", {countries[0]}"
    else:
        where = ", ".join(named) if len(named) <= 3 else f"{len(countries)} countries"
        biggest = "biggest city" if options["city_count"] == 1 else             f"{options['city_count']} biggest cities"
        where += f", {biggest}" + (" each" if len(countries) > 1 else "")
    return f"{niches} in {where}"


def passes(lead: dict, options: dict) -> bool:
    return why_not(lead, options) is None


def why_not(lead: dict, options: dict) -> str | None:
    """Why a filter that Google's data alone decides leaves this lead out; None if it fits."""
    if options["where"] == "area":
        if options["area_lat"] is not None:  # the map views are squares; keep the circle
            if lead.get("latitude") is None or geo.distance_km(
                    options["area_lat"], options["area_lng"], lead["latitude"],
                    lead["longitude"]) > float(options["area_km"]):
                return "outside the area"
    else:
        codes = {geo.country_code(c) for c in geo.expand(options["countries"])} - {""}
        code = lead.get("country_code")
        # Ambiguous city names ("Hyderabad", "Victoria") can pull in another country, and
        # a hidden address with its pin far from the city searched has no country at all
        if codes and (code or lead.get("address") == SERVICE_AREA) and code not in codes:
            return "outside the chosen countries"
    if options["skip_closed"] and lead.get("status") != "Open":
        return "closed"
    rating, reviews = lead.get("rating") or 0, lead.get("reviews") or 0
    if rating < float(options["min_rating"] or 0):
        return "rating too low"
    if reviews < int(options["min_reviews"] or 0):
        return "too few reviews"
    if float(options["max_rating"] or 0) and rating > float(options["max_rating"]):
        return "rating too high"
    if int(options["max_reviews"]) >= 0 and reviews > int(options["max_reviews"]):
        return "too many reviews"
    if options["website"] != "any" and bool(lead.get("website")) != (options["website"] == "yes"):
        return "no website" if options["website"] == "yes" else "has a website"
    if options["require_phone"] and not lead.get("phone"):
        return "no phone number"
    if options["require_address"] and lead.get("address") in ("", SERVICE_AREA):
        return "address hidden"
    if not passes_hours(lead.get("hours") or "", lead.get("timezone"), options):
        return "not open at the chosen times"
    return None


# --- picking the best -------------------------------------------------------
def quality(lead: dict) -> int:
    """0-100 from the facts alone: how reachable and established the business looks."""
    socials = sum(str(lead.get(k) or "").startswith("http") for k in
                  ("facebook", "instagram", "linkedin", "twitter", "youtube", "tiktok"))
    rating, reviews = lead.get("rating") or 0, lead.get("reviews") or 0
    points = (15 * bool(lead.get("phone")) + 15 * bool(lead.get("website"))
              + 15 * bool(lead.get("emails")) + 10 * (rating >= 4) + 5 * (rating >= 4.5)
              + min(15, round(5 * math.log10(1 + reviews)))  # 15 at 1,000 reviews
              + 10 * (lead.get("claimed") == "Yes")
              + 5 * (lead.get("address") not in ("", None, SERVICE_AREA))
              + 5 * bool(lead.get("hours")) + min(5, 2 * socials))
    return min(100, points)


def score(lead: dict) -> float:
    """The quality score, averaged with the AI score once Smart mode has given one."""
    base = lead.get("quality", 0)
    return (base + lead["ai_score"]) / 2 if "ai_score" in lead else base


def balanced(leads: list[dict], key) -> list[dict]:
    """Best first, taking turns between the searches (city and business type) that found
    them: the first N are every search's best few, so no city or business type gets more
    than its share unless the others run out."""
    groups: dict[str, list[dict]] = {}
    for lead in sorted(leads, key=key, reverse=True):
        groups.setdefault(lead.get("query", ""), []).append(lead)
    turn = {id(lead): n for group in groups.values() for n, lead in enumerate(group)}
    return sorted(leads, key=lambda lead: (turn[id(lead)], -key(lead)))


def passes_hours(text: str, timezone: str | None, options: dict) -> bool:
    if options["open_now"] and not hours.open_now(text, timezone):
        return False
    if options["open_24h"] and not hours.always_open(text):
        return False
    if options["open_weekends"] and not hours.open_weekends(text):
        return False
    if options["open_at"]:
        hour, _, minute = str(options["open_time"]).partition(":")
        if not hours.open_at(text, int(options["open_day"]), int(hour) * 60 + int(minute or 0)):
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


def mark_query_done(search_id: int, query: str, capped: bool = False) -> None:
    """``capped``: stopped once it had found its share, with more left on Google."""
    progress = get(search_id)["progress"]
    done = progress.setdefault("done", [])
    if query not in done:
        done.append(query)
    rest = [q for q in progress.get("capped", []) if q != query]
    progress["capped"] = rest + [query] if capped else rest
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
    """Merge extra fields (emails, AI score...) into a saved lead and its candidate."""
    conn = db.connect()
    for table in ("leads", "candidates"):
        row = conn.execute(f"SELECT data FROM {table} WHERE search_id = ? AND place_id = ?",
                           (search_id, place_id)).fetchone()
        if row is not None:
            data = {**json.loads(row["data"]), **fields}
            conn.execute(f"UPDATE {table} SET data = ? WHERE search_id = ? AND place_id = ?",
                         (json.dumps(data, ensure_ascii=False), search_id, place_id))
    conn.commit()


# --- candidates: everything Google listed, to pick the leads from -------------
KNOWN = "found by an earlier search"
REMOVED = "deleted by you"


def save_candidates(search_id: int, found: list[dict], options: dict) -> list[dict]:
    """Store businesses from Google with why each is left out, if it is; return the new
    ones that fit."""
    conn = db.connect()
    fits = []
    for lead in found:
        dropped = why_not(lead, options)
        if dropped is None and options["skip_known"] and conn.execute(
                "SELECT 1 FROM leads WHERE place_id = ? AND search_id != ?",
                (lead["place_id"], search_id)).fetchone():
            dropped = KNOWN
        lead = {**lead, "quality": quality(lead)}
        if conn.execute("INSERT OR IGNORE INTO candidates(search_id, place_id, data, dropped) "
                        "VALUES(?, ?, ?, ?)", (search_id, lead["place_id"],
                                               json.dumps(lead, ensure_ascii=False),
                                               dropped)).rowcount and dropped is None:
            fits.append(lead)
    conn.commit()
    return fits


def candidates(search_id: int) -> list[dict]:
    """The candidates that fit, oldest first."""
    return [json.loads(r["data"]) for r in db.query(
        "SELECT data FROM candidates WHERE search_id = ? AND dropped IS NULL ORDER BY rowid",
        (search_id,))]


def check_candidate(search_id: int, place_id: str, fields: dict, dropped: str | None) -> None:
    """Website or AI check results for a candidate, with the quality score brought up to date,
    and why it is now left out (or None)."""
    conn = db.connect()
    row = conn.execute("SELECT data FROM candidates WHERE search_id = ? AND place_id = ?",
                       (search_id, place_id)).fetchone()
    if row is None:
        return
    data = {**json.loads(row["data"]), **fields}
    data["quality"] = quality(data)
    conn.execute("UPDATE candidates SET data = ?, dropped = ? WHERE search_id = ? AND place_id = ?",
                 (json.dumps(data, ensure_ascii=False), dropped, search_id, place_id))
    conn.commit()


def dropped_counts(search_id: int) -> dict[str, int]:
    """Why candidates were left out: reason -> how many, most common first."""
    return {r["dropped"]: r["n"] for r in db.query(
        "SELECT dropped, COUNT(*) AS n FROM candidates WHERE search_id = ? AND dropped IS NOT NULL "
        "GROUP BY dropped ORDER BY n DESC", (search_id,))}


def undrop(search_id: int, reasons: tuple[str, ...]) -> None:
    """Let candidates left out for these reasons back in (the user relaxed that filter)."""
    db.execute_many("UPDATE candidates SET dropped = NULL WHERE search_id = ? AND dropped = ?",
                    [(search_id, reason) for reason in reasons])


def adopt_leads(search_id: int) -> None:
    """Searches from before candidates existed: their leads become the candidates."""
    db.execute("INSERT OR IGNORE INTO candidates(search_id, place_id, data) "
               "SELECT search_id, place_id, data FROM leads WHERE search_id = ?", (search_id,))


def set_picked(search_id: int, picked: list[dict]) -> None:
    """Make these (best first) the search's leads, replacing any picked before."""
    db.execute("DELETE FROM leads WHERE search_id = ?", (search_id,))
    save_leads(search_id, picked)


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
    db.execute("DELETE FROM candidates WHERE search_id = ?", (search_id,))
    db.execute("DELETE FROM searches WHERE id = ?", (search_id,))


def set_options(search_id: int, options: dict) -> None:
    """Change a saved search (more cities, a relaxed filter); resuming then uses these."""
    options = options_with_defaults(options)
    db.execute("UPDATE searches SET options = ?, title = ? WHERE id = ?",
               (json.dumps(options), title(options), search_id))


def set_fields(search_id: int, fields: list[str]) -> None:
    """The columns a search shows, changed on the Leads page."""
    record = get(search_id)
    if record is not None:
        set_options(search_id, {**record["options"], "fields": fields})


def delete_leads(place_ids: list[str], search_id: int = 0) -> None:
    """Leads the user deleted: from one search, or with ``search_id`` 0 from every search."""
    rows = [(place_id, search_id, search_id) for place_id in place_ids]
    db.execute_many("DELETE FROM leads WHERE place_id = ? AND (? = 0 OR search_id = ?)", rows)
    # so resuming the search does not pick them again
    db.execute_many("UPDATE candidates SET dropped = ? "
                    "WHERE place_id = ? AND (? = 0 OR search_id = ?)",
                    [(REMOVED, *row) for row in rows])


def recover_interrupted() -> None:
    """At start-up nothing is running, so a 'running' search was cut off by closing the app."""
    db.execute("UPDATE searches SET status = 'stopped' WHERE status = 'running'")
