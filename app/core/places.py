"""Turn one Google Maps search result (a deeply nested JSON array) into a flat lead.

Google does not document this format. The positions below were mapped by hand
on 2026-10-16 from real responses; ``tests/fixtures/maps_page.json`` is one of
those responses, so a test fails loudly if a position is ever read wrong. If
Google moves things, fix the index here and refresh the fixture.
"""
from __future__ import annotations

import json
from urllib.parse import quote_plus

# (key, column header). The order here is the column order in the table and the export.
# Keys added later by enrichment and the AI check are listed too, so the columns exist
# from the start and stay blank until filled.
FIELDS = [
    ("name", "Name"),
    ("quality", "Quality score"),
    ("ai_score", "AI score"),
    ("ai_verdict", "AI verdict"),
    ("ai_reason", "AI reason"),
    ("category", "Category"),
    ("owner_name", "Owner"),
    ("owner_source", "Owner found in"),
    ("owner_linkedin", "Owner on LinkedIn"),
    ("phone", "Phone"),
    ("phone_international", "Phone (international)"),
    ("emails", "Emails"),
    ("website", "Website"),
    ("domain", "Domain"),
    ("facebook", "Facebook"),
    ("instagram", "Instagram"),
    ("linkedin", "LinkedIn"),
    ("twitter", "X / Twitter"),
    ("youtube", "YouTube"),
    ("tiktok", "TikTok"),
    ("rating", "Rating"),
    ("reviews", "Reviews"),
    ("price", "Price"),
    ("company_age", "Company age (estimated)"),
    ("domain_created", "Website since"),
    ("age_source", "Age based on"),
    ("status", "Status"),
    ("address", "Address"),
    ("street", "Street"),
    ("neighborhood", "Area"),
    ("city", "City"),
    ("postal_code", "Postal code"),
    ("state", "State"),
    ("country_code", "Country"),
    ("latitude", "Latitude"),
    ("longitude", "Longitude"),
    ("categories", "All categories"),
    ("description", "Description"),
    ("hours", "Opening hours"),
    ("claimed", "Claimed by owner"),
    ("attributes", "Features"),
    ("timezone", "Time zone"),
    ("local_name", "Local name"),
    ("maps_url", "Google Maps link"),
    ("reviews_url", "Reviews link"),
    ("photo", "Photo"),
    ("place_id", "Place ID"),
    ("query", "Found by search"),
]
HEADERS = dict(FIELDS)
SERVICE_AREA = "Service area (address hidden on Google)"
NOT_FOUND = "N/A"  # looked for on the business's website and not there (LinkedIn columns)
# How the columns are grouped where the user picks them (New search, Leads > Columns).
# Every key of FIELDS appears exactly once.
FIELD_GROUPS = [
    ("Business", ["name", "quality", "category", "categories", "description", "status", "hours", "price",
                  "attributes", "claimed", "local_name"]),
    ("Owner", ["owner_name", "owner_source", "owner_linkedin"]),
    ("Contact", ["phone", "phone_international", "emails", "website", "domain"]),
    ("Social media", ["facebook", "instagram", "linkedin", "twitter", "youtube", "tiktok"]),
    ("Reviews", ["rating", "reviews", "reviews_url"]),
    ("Location", ["address", "street", "neighborhood", "city", "postal_code", "state",
                  "country_code", "latitude", "longitude", "timezone", "maps_url"]),
    ("Company age", ["company_age", "domain_created", "age_source"]),
    ("Smart mode", ["ai_score", "ai_verdict", "ai_reason"]),
    ("Other", ["photo", "place_id", "query"]),
]


def at(obj, *path):
    """obj[a][b][c]... or None if any step is missing. Google omits empty branches."""
    for key in path:
        try:
            obj = obj[key]
        except (IndexError, KeyError, TypeError):
            return None
    return obj


def results(response: list) -> list[list]:
    """The raw place arrays in one decoded search response."""
    items = at(response, 64) or []
    return [item[1] for item in items if isinstance(at(item, 1), list)]


def _clean(text):
    # Google uses narrow no-break spaces and en dashes in opening hours
    return text.replace(" ", " ").replace("–", "-").strip() if isinstance(text, str) else text


def _hours(place) -> str:
    days = at(place, 203, 0) or []
    rows = []
    for day in sorted(days, key=lambda d: at(d, 1) or 0):
        name = at(day, 0)
        times = ", ".join(_clean(at(t, 0)) for t in (at(day, 3) or []) if at(t, 0))
        if name and times:
            rows.append(f"{name}: {times}")
    return "; ".join(rows)


def _attributes(place) -> str:
    names = []
    for group in at(place, 100, 1) or []:
        for item in at(group, 2) or []:
            if isinstance(at(item, 1), str):
                names.append(item[1])
    return ", ".join(dict.fromkeys(names))


def _status(place) -> str:
    text = json.dumps([at(place, 203), at(place, 88), at(place, 118)], ensure_ascii=False)
    for status in ("Permanently closed", "Temporarily closed"):
        if status in text:
            return status
    return "Open"


def parse(place: list, query: str = "") -> dict | None:
    """One lead, or None for something that is not a business (no place ID or name)."""
    place_id, name = at(place, 78), at(place, 11)
    if not place_id or not name:
        return None
    parts = at(place, 183, 1) or []
    categories = at(place, 13) or []
    price = at(place, 4, 2) or at(place, 4, 10)
    description = at(place, 32, 1, 1) or at(place, 32, 0, 1) or ""
    lead = {
        "place_id": place_id,
        "name": name,
        "category": categories[0] if categories else "",
        "categories": ", ".join(categories),
        "phone": at(place, 178, 0, 0) or "",
        "phone_international": at(place, 178, 0, 3) or "",
        "website": at(place, 7, 0) or "",
        "domain": at(place, 7, 1) or "",
        "rating": at(place, 4, 7),
        "reviews": at(place, 4, 8) or 0,
        "price": price if isinstance(price, str) else "",
        "status": _status(place),
        # Businesses that visit their customers may hide their address; Google then only
        # gives a rough pin, which scraper.search checks against the place searched
        "address": at(place, 39) or at(place, 18) or SERVICE_AREA,
        "street": at(parts, 1) or "",
        "neighborhood": at(parts, 0) or "",
        # [166] is "City, Country"; the only place the city appears in some countries (UAE)
        "city": at(parts, 3) or (at(place, 166) or "").split(",")[0].strip(),
        "postal_code": at(parts, 4) or "",
        "state": at(parts, 5) or "",
        "country_code": at(parts, 6) or at(place, 243) or "",
        "latitude": at(place, 9, 2),
        "longitude": at(place, 9, 3),
        "description": description if isinstance(description, str) else "",
        "hours": _hours(place),
        # [57] is the business's own Google account; only claimed listings have one
        "claimed": "Yes" if at(place, 57, 2) else "No",
        "attributes": _attributes(place),
        "timezone": at(place, 30) or "",
        "local_name": at(place, 101) or "",
        "maps_url": ("https://www.google.com/maps/search/?api=1&query="
                     f"{quote_plus(name)}&query_place_id={place_id}"),
        "reviews_url": at(place, 4, 3, 0) or "",
        "photo": at(place, 37, 0, 0, 6, 0) or "",
        "query": query,
    }
    return lead
