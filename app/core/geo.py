"""Countries, regions and their biggest cities, from the bundled GeoNames extract."""
from __future__ import annotations

import json
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
