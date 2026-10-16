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
searched city by city.
"""
from __future__ import annotations

import json
from typing import Callable, Iterator

import httpx

from app import config
from app.core import places

PAGE_SIZE = 20
MAX_OFFSET = 400  # Google runs dry near 200; this only guards against an endless loop
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


class MapsClient:
    """One HTTP connection pool, safe to share between threads."""

    def __init__(self, language: str = "en"):
        self.language = language
        self.template = config.resource_path("app/data/maps_pb.txt").read_text("utf-8").strip()
        # From an EU or UK connection Google first redirects to its cookie-consent page;
        # these cookies record "reject all", which is what a visitor who said no would carry
        self.http = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": f"{language},en;q=0.8"},
            cookies={"CONSENT": "PENDING+987",
                     "SOCS": "CAESHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmVuIAEaBgiAo_CmBg"},
            timeout=25, follow_redirects=False)

    def close(self) -> None:
        self.http.close()

    def fetch(self, query: str, offset: int = 0, view: list | None = None) -> list:
        if view is None:
            pb = f"!1s{query}!7i{PAGE_SIZE}" + self.template
        else:
            distance, lng, lat = view
            pb = (f"!4m12!1m3!1d{distance}!2d{lng}!3d{lat}!2m3!1f0!2f0!3f0!3m2!1i1024!2i768"
                  f"!4f13.1!7i{PAGE_SIZE}!8i{offset}" + self.template)
        params = {"tbm": "map", "authuser": "0", "hl": self.language, "q": query, "pb": pb}
        response = self.http.get("https://www.google.com/search", params=params)
        location = response.headers.get("location", "")
        if response.status_code in (429, 403) or (response.is_redirect and "sorry" in location):
            raise Blocked("Google is limiting requests from this connection")
        if response.is_redirect and "consent." in location:
            raise httpx.HTTPError("Google asked for cookie consent; the consent cookie needs "
                                  "refreshing in app/core/scraper.py")
        response.raise_for_status()
        return decode(response.text)


def search(client: MapsClient, query: str,
           cancelled: Callable[[], bool] = lambda: False) -> Iterator[list[dict]]:
    """Yield the leads on each page of one search until Google runs out of new ones."""
    response = client.fetch(query)
    view = places.at(response, 1, 0)
    seen: set[str] = set()

    def new_leads(resp: list) -> list[dict]:
        found = []
        for raw in places.results(resp):
            lead = places.parse(raw, query)
            if lead and lead["place_id"] not in seen:
                seen.add(lead["place_id"])
                found.append(lead)
        return found

    page = new_leads(response)
    offset = 0
    while page:
        yield page
        offset += PAGE_SIZE
        if not view or offset > MAX_OFFSET or cancelled():
            return
        page = new_leads(client.fetch(query, offset, view))
