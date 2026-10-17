"""Google Maps search over plain HTTPS: no browser, no API key.

The Google Maps web page fetches its result list from
``/search?tbm=map&q=...&pb=...`` as JSON, 20 places at a time. We make the same
request directly. ``pb`` is a long parameter string Google's own page sends; the
fixed part of it lives in ``app/data/maps_pb.txt`` (captured 2026-10-16), and we
only put the paging and map position in front of it:

* page 1:  ``!1s<query>!7i20`` + template, and Google answers with where on the
  map it looked (``response[1][0]`` = distance, longitude, latitude)
* page 2+: ``!4m12!1m3!1d<distance>!2d<lng>!3d<lat>...!7i20!8i<offset>`` + template

Google stops at roughly 200 results for one search, which is why a country is
searched city by city, and an area around a place map view by map view: a query ending
in "@lat,lng,camera" asks for the business type alone with the map put there
("dentist near Dubai Marina @25.08,55.13,21739").
"""
from __future__ import annotations

import itertools
import json
import re
import threading
from typing import Callable, Iterator

import httpx

from app import config
from app.core import credentials, geo, places

PAGE_SIZE = 20
MAX_OFFSET = 400  # Google runs dry near 200; this only guards against an endless loop
AREA = re.compile(r"^(.*) @(-?[\d.]+),(-?[\d.]+),(\d+)$")
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0")


class Blocked(RuntimeError):
    """Google asked us to slow down (a 429, or a redirect to its 'unusual traffic' page)."""


def decode(text: str) -> list:
    """Google wraps the JSON two ways: a ``)]}'`` prefix, or that inside {"c":..,"d":".."}."""
    text = text.strip()
    if text.startswith("{"):
        text = json.loads(text[: text.rfind("}") + 1])["d"]
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[1]
    return json.loads(text)


PROXIES_SECRET = "proxies"


def parse_proxies(text: str) -> tuple[list[str], list[str]]:
    """One proxy per line -> (proxy URLs, lines that are not proxies).

    Accepts host:port, user:pass@host:port, host:port:user:pass and any of those
    after http://, https://, socks5:// or socks5h://. No scheme means HTTP.
    """
    good, bad = [], []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        scheme, sep, rest = line.partition("://")
        if not sep:
            scheme, rest = "http", line
        parts = rest.split(":")
        if "@" not in rest and len(parts) == 4:  # host:port:user:pass, as many providers list them
            rest = f"{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        try:
            url = httpx.URL(f"{scheme.lower()}://{rest}")
            ok = url.scheme in ("http", "https", "socks5", "socks5h") and url.host and url.port
        except (httpx.InvalidURL, ValueError, TypeError):
            ok = False
        (good if ok else bad).append(f"{scheme.lower()}://{rest}" if ok else line)
    return good, bad


def saved_proxies() -> list[str]:
    """The proxies from Settings (kept encrypted, since they often hold a password)."""
    return parse_proxies(credentials.load_secret(PROXIES_SECRET))[0]


def check_proxy(proxy: str) -> str | None:
    """None if Google answers through this proxy, else what went wrong (for Settings > Test)."""
    try:
        response = httpx.get("https://www.google.com/generate_204", proxy=proxy, timeout=12,
                             headers={"User-Agent": USER_AGENT})
    except httpx.HTTPError as error:
        return type(error).__name__.replace("Error", " error").replace("Exception", "").strip()
    return None if response.status_code == 204 else f"Google answered {response.status_code}"


class MapsClient:
    """HTTP connection pools (one per proxy, or one direct), safe to share between threads."""

    def __init__(self, language: str = "en", proxies: list[str] | None = None):
        self.language = language
        self.template = config.resource_path("app/data/maps_pb.txt").read_text("utf-8").strip()
        proxies = saved_proxies() if proxies is None else proxies
        self.clients = [self._client(proxy) for proxy in proxies] or [self._client(None)]
        self._turn = itertools.cycle(range(len(self.clients)))
        self._lock = threading.Lock()

    def _client(self, proxy: str | None) -> httpx.Client:
        # From an EU or UK connection Google first redirects to its cookie-consent page;
        # these cookies record "reject all", which is what a visitor who said no would carry
        return httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": f"{self.language},en;q=0.8"},
            cookies={"CONSENT": "PENDING+987",
                     "SOCS": "CAESHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmVuIAEaBgiAo_CmBg"},
            timeout=25, follow_redirects=False, proxy=proxy)

    def close(self) -> None:
        for client in self.clients:
            client.close()

    def fetch(self, query: str, offset: int = 0, view: list | None = None) -> list:
        """One results page, through the next proxy in turn. A proxy that Google limits or
        that does not answer is skipped; Blocked only when every proxy was limited."""
        with self._lock:
            first = next(self._turn)
        blocked: Blocked | None = None
        last: Exception | None = None
        for step in range(len(self.clients)):
            client = self.clients[(first + step) % len(self.clients)]
            try:
                return self._fetch(client, query, offset, view)
            except Blocked as error:
                blocked = error
            except (httpx.ProxyError, httpx.ConnectError, httpx.TimeoutException) as error:
                if len(self.clients) == 1:
                    raise
                last = error
        if blocked is not None:  # pause the search, so it can be resumed later
            raise blocked
        raise httpx.ConnectError(f"None of the proxies in Settings answered ({last})")

    def _fetch(self, client: httpx.Client, query: str, offset: int, view: list | None) -> list:
        if view is None:
            pb = f"!1s{query}!7i{PAGE_SIZE}" + self.template
        else:
            distance, lng, lat = view
            pb = (f"!4m12!1m3!1d{distance}!2d{lng}!3d{lat}!2m3!1f0!2f0!3f0!3m2!1i1024!2i768"
                  f"!4f13.1!7i{PAGE_SIZE}!8i{offset}" + self.template)
        params = {"tbm": "map", "authuser": "0", "hl": self.language, "q": query, "pb": pb}
        response = client.get("https://www.google.com/search", params=params)
        location = response.headers.get("location", "")
        if response.status_code in (429, 403) or (response.is_redirect and "sorry" in location):
            raise Blocked("Google is limiting requests from this connection")
        if response.is_redirect and "consent." in location:
            raise httpx.HTTPError("Google asked for cookie consent; the consent cookie needs "
                                  "refreshing in app/core/scraper.py")
        response.raise_for_status()
        return decode(response.text)


def locate(client: MapsClient, place: str) -> tuple[float, float] | None:
    """Where Google Maps centres the map for a typed place: (latitude, longitude)."""
    view = places.at(client.fetch(place), 1, 0)
    if not view or len(view) < 3 or not all(isinstance(v, (int, float)) for v in view[1:3]):
        return None
    return view[2], view[1]


SERVICE_AREA_KM = 50


def near_place(lead: dict, query: str, view: list | None) -> None:
    """A business that hides its address: if its rough pin is near the searched city, it is
    in that city ("dentist in Dubai, United Arab Emirates"). A pin far away (some sit on
    another continent) gets no country, which the country filter then leaves out."""
    if not view or lead.get("latitude") is None or geo.distance_km(
            view[2], view[1], lead["latitude"], lead["longitude"]) > SERVICE_AREA_KM:
        return
    city, _, country = query.rpartition(" in ")[2].rpartition(", ")
    lead["city"] = lead["city"] or city
    lead["country_code"] = lead["country_code"] or geo.country_code(geo.resolve(country) or "")


def search(client: MapsClient, query: str,
           cancelled: Callable[[], bool] = lambda: False) -> Iterator[list[dict]]:
    """Yield the leads on each page of one search until Google runs out of new ones."""
    area = AREA.match(query)
    if area:
        label = area.group(1)
        text = label.split(" near ", 1)[0]  # the business type; the map says where
        view = [int(area.group(4)), float(area.group(3)), float(area.group(2))]
        response = client.fetch(text, 0, view)
    else:
        label = text = query
        response = client.fetch(query)
        view = places.at(response, 1, 0)
    seen: set[str] = set()

    def new_leads(resp: list) -> list[dict]:
        found = []
        for raw in places.results(resp):
            lead = places.parse(raw, label)
            if lead and lead["place_id"] not in seen:
                seen.add(lead["place_id"])
                if not area and lead["address"] == places.SERVICE_AREA:
                    near_place(lead, label, view)
                found.append(lead)
        return found

    def leaves_view(page: list[dict]) -> bool:
        """Google pages outwards past the map view; once a page has nothing inside the
        view (measured: page 4 or 5 of a 3 km view), the rest is too far away to keep."""
        reach = view[0] * geo.VIEW_PER_METRE / 1000 * 0.71
        return not any(geo.distance_km(view[2], view[1], lead["latitude"], lead["longitude"])
                       <= reach for lead in page if lead.get("latitude") is not None)

    page = new_leads(response)
    offset = 0
    while page:
        yield page
        offset += PAGE_SIZE
        if not view or offset > MAX_OFFSET or cancelled() or (area and leaves_view(page)):
            return
        page = new_leads(client.fetch(text, offset, view))
