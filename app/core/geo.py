"""Countries and their biggest cities, from the bundled GeoNames extract."""
from __future__ import annotations

import json
from functools import lru_cache

from app import config


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(config.resource_path("app/data/cities.json").read_text("utf-8"))


def countries() -> list[str]:
    return list(_data())


def country_code(country: str) -> str:
    return _data().get(country, {}).get("code", "")


def cities(country: str) -> list[str]:
    return list(_data().get(country, {}).get("cities", []))
