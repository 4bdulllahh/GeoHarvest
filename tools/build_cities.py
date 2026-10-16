"""Build app/data/cities.json from GeoNames (CC BY 4.0, https://www.geonames.org).

For every country: its name and its biggest cities (population 15,000+), largest
first. The app sweeps these when the user picks a country but no city.

    python tools/build_cities.py
"""
import io
import json
import zipfile
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "cities.json"
PER_COUNTRY = 60  # Google caps a search at ~200 results, so 60 cities covers a country well


def main() -> None:
    base = "https://download.geonames.org/export/dump/"
    countries = {}
    for line in httpx.get(base + "countryInfo.txt", timeout=60).text.splitlines():
        if line and not line.startswith("#"):
            cols = line.split("\t")
            countries[cols[0]] = cols[4]

    archive = zipfile.ZipFile(io.BytesIO(httpx.get(base + "cities15000.zip", timeout=120).content))
    cities: dict[str, list[tuple[int, str, str]]] = {}
    for line in archive.read("cities15000.txt").decode("utf-8").splitlines():
        cols = line.split("\t")
        # name, country code, admin1 code, population; skip city districts (PPLX)
        if cols[7] == "PPLX":
            continue
        cities.setdefault(cols[8], []).append((int(cols[14] or 0), cols[1], cols[10]))

    data = {}
    for code, name in sorted(countries.items(), key=lambda item: item[1]):
        found = sorted(cities.get(code, []), reverse=True)
        names, seen = [], set()
        for _pop, city, _admin in found:
            if city not in seen:
                seen.add(city)
                names.append(city)
            if len(names) == PER_COUNTRY:
                break
        if names:
            data[name] = {"code": code, "cities": names}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(data)} countries -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
