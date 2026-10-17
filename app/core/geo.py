"""Countries, regions and their biggest cities, from the bundled GeoNames extract."""
from __future__ import annotations

import json
import math
from functools import lru_cache

from app import config

# Regions expand to their member countries (ISO codes)
REGIONS = {
    "European Union": ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
                       "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
                       "SI", "ES", "SE"],
    "Gulf (GCC)": ["AE", "SA", "QA", "KW", "BH", "OM"],
}
# What people type, mapped to the name in the list
ALIASES = {
    "usa": "United States", "us": "United States", "america": "United States",
    "united states of america": "United States", "uk": "United Kingdom",
    "great britain": "United Kingdom", "britain": "United Kingdom", "england": "United Kingdom",
    "uae": "United Arab Emirates", "emirates": "United Arab Emirates", "ksa": "Saudi Arabia",
    "eu": "European Union", "europe": "European Union", "gcc": "Gulf (GCC)",
    "gulf": "Gulf (GCC)", "holland": "Netherlands", "the netherlands": "Netherlands",
    "czech republic": "Czechia", "korea": "South Korea", "turkiye": "Turkey",
}


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(config.resource_path("app/data/cities.json").read_text("utf-8"))


@lru_cache(maxsize=1)
def _by_code() -> dict[str, str]:
    return {info["code"]: name for name, info in _data().items()}


def countries() -> list[str]:
    return list(_data())


def choices() -> list[str]:
    """What the Country box offers: the regions first, then every country."""
    return list(REGIONS) + countries()


def resolve(name: str) -> str | None:
    """The proper country or region name for what was typed, or None if unknown."""
    text = name.strip()
    lowered = text.lower()
    if lowered in ALIASES:
        return ALIASES[lowered]
    for known in choices():
        if known.lower() == lowered:
            return known
    return None


def expand(names: list[str]) -> list[str]:
    """Country names, with regions replaced by their members, each country once."""
    found: list[str] = []
    for name in names:
        proper = resolve(name)
        members = [_by_code()[c] for c in REGIONS[proper] if c in _by_code()] \
            if proper in REGIONS else [proper] if proper else []
        found += [m for m in members if m not in found]
    return found


def country_code(country: str) -> str:
    return _data().get(country, {}).get("code", "")


def cities(country: str) -> list[str]:
    return list(_data().get(country, {}).get("cities", []))


# --- searching around a point ---------------------------------------------------
KM_PER_DEGREE = 111.32
MAX_CELLS_ACROSS = 8   # a radius search is at most 8 x 8 map views per business type
CELL_KM = 5            # Google lists about 200 places per view, so keep views small
# Google's map position is a camera height; it sees about this many metres of ground per metre
VIEW_PER_METRE = 0.23


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance (haversine)."""
    p = math.pi / 180
    a = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lng2 - lng1) * p)) / 2)
    return 12742 * math.asin(math.sqrt(a))


def radius_cells(lat: float, lng: float, km: float) -> list[tuple[float, float, int]]:
    """Map views (lat, lng, camera distance in metres) that together cover the circle."""
    across = min(MAX_CELLS_ACROSS, max(1, math.ceil(2 * km / CELL_KM)))
    size = 2 * km / across
    cells = []
    for row in range(across):
        for col in range(across):
            dy = -km + size * (row + 0.5)
            dx = -km + size * (col + 0.5)
            if math.hypot(dx, dy) > km + size * 0.71:  # this square misses the circle
                continue
            cell_lat = lat + dy / KM_PER_DEGREE
            cell_lng = lng + dx / (KM_PER_DEGREE * max(math.cos(math.radians(lat)), 0.01))
            cells.append((round(cell_lat, 5), round(cell_lng, 5),
                          round(size * 1000 / VIEW_PER_METRE)))
    return cells
