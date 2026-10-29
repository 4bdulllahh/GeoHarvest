"""Business logic tests. No network, no UI: run with  python -m pytest tests/ -q"""
import json
from pathlib import Path

import pytest

from app.core import db, places, scraper
from app.core import search as searches

FIXTURE = Path(__file__).parent / "fixtures" / "maps_page.json"


@pytest.fixture
def page():
    return json.loads(FIXTURE.read_text("utf-8"))


@pytest.fixture
def fresh_db(tmp_path):
    db.close()
    db.init(tmp_path / "test.db")
    yield
    db.close()


# --- decoding and parsing ---------------------------------------------------
def test_decode_both_wrappings():
    body = '[["x"],[1,2]]'
    assert scraper.decode(")]}'\n" + body) == [["x"], [1, 2]]
    assert scraper.decode(json.dumps({"c": 0, "d": ")]}'\n" + body}) + '/*""*/') == [["x"], [1, 2]]


def test_parse_real_result(page):
    leads = [places.parse(raw, "restaurants in Lahore") for raw in places.results(page)]
    assert [lead["name"] for lead in leads] == [
        "Monal Lahore", "Haveli Restaurant", "Café Aylanto", "The Garden Spice"]
    haveli = leads[1]
    assert haveli["place_id"] == "ChIJ-4k3_J0cGTkRSqffwzEB0yI"
    assert haveli["phone_international"] == "+923008414899"
    assert haveli["website"] == "http://www.haveli.com.pk/"
    assert haveli["domain"] == "haveli.com.pk"
    assert haveli["rating"] == 4.2 and haveli["reviews"] == 19259
    assert haveli["city"] == "Lahore" and haveli["postal_code"] == "54000"
    assert haveli["country_code"] == "PK"
    assert haveli["category"] == "Pakistani restaurant"
    assert round(haveli["latitude"], 2) == 31.59
    assert haveli["hours"].startswith("Monday: ")
    assert "Wheelchair-accessible entrance" in haveli["attributes"]
    assert haveli["claimed"] == "Yes"
    assert haveli["status"] == "Open"
    assert haveli["query"] == "restaurants in Lahore"
    # every parsed key is a known column, so nothing is silently left out of exports
    assert set(haveli) <= set(places.HEADERS)


def test_parse_skips_non_places():
    assert places.parse([]) is None
    assert places.parse([None] * 80) is None


# --- paging -----------------------------------------------------------------
class FakeClient:
    """Serves the fixture page, then the same places again (Google's overlap), then nothing."""

    def __init__(self, page):
        self.page = page
        self.calls = []

    def fetch(self, query, offset=0, view=None):
        self.calls.append((offset, view is not None))
        if offset == 0:
            return self.page
        if offset == 20:
            return self.page  # all repeats: the search must end here
        raise AssertionError("asked for a page after the results ran out")


def test_search_pages_until_no_new_results(page):
    client = FakeClient(page)
    pages = list(scraper.search(client, "q"))
    assert len(pages) == 1 and len(pages[0]) == 4
    assert client.calls == [(0, False), (20, True)]


def test_search_stops_when_cancelled(page):
    client = FakeClient(page)
    assert len(list(scraper.search(client, "q", cancelled=lambda: True))) == 1
    assert client.calls == [(0, False)]


# --- queries and filters ----------------------------------------------------
def test_queries_from_cities_or_country():
    chosen = {"niches": ["dentist", " "], "countries": ["Pakistan"], "cities": ["Lahore", "Multan"]}
    assert searches.build_queries(chosen) == [
        "dentist in Lahore, Pakistan", "dentist in Multan, Pakistan"]
    sweep = searches.build_queries({"niches": ["cafe", "bakery"], "countries": ["USA"],
                                    "city_count": 2})
    assert sweep == ["cafe in New York City, United States", "bakery in New York City, United States",
                     "cafe in Los Angeles, United States", "bakery in Los Angeles, United States"]
    assert searches.title({"niches": ["cafe"], "countries": ["uae"], "city_count": 2}) ==         "cafe in United Arab Emirates, 2 biggest cities"
    # old saved searches had one "country"
    assert searches.build_queries({"niches": ["cafe"], "country": "Germany", "city_count": 1}) == [
        "cafe in Berlin, Germany"]


def test_regions_and_several_countries():
    from app.core import geo

    eu = geo.expand(["European Union"])
    assert len(eu) == 27 and "Germany" in eu and "Netherlands" in eu
    assert geo.expand(["UK", "Germany", "EU"])[:2] == ["United Kingdom", "Germany"]
    assert len(geo.expand(["UK", "Germany", "EU"])) == 28  # Germany only once
    assert geo.resolve("holland") == "Netherlands" and geo.resolve("Atlantis") is None

    options = {"niches": ["lawyer"], "countries": ["Gulf (GCC)"], "city_count": 1}
    queries = searches.build_queries(options)
    assert len(queries) == 6 and "lawyer in Dubai, United Arab Emirates" in queries
    assert searches.title(options) == "lawyer in Gulf (GCC), biggest city each"
    ticked = {**options, "cities": ["Dubai, United Arab Emirates", "Doha, Qatar", "Al Barsha"]}
    assert searches.build_queries(ticked) == ["lawyer in Dubai, United Arab Emirates",
                                              "lawyer in Doha, Qatar", "lawyer in Al Barsha"]
    assert searches.title(ticked) == "lawyer in 3 cities in 6 countries"
    full = searches.options_with_defaults(options)
    assert searches.passes({"country_code": "QA", "status": "Open"}, full)
    assert not searches.passes({"country_code": "US", "status": "Open"}, full)


def test_filters():
    options = searches.options_with_defaults(
        {"countries": ["Pakistan"], "min_rating": 4, "min_reviews": 10, "require_website": True})
    good = {"country_code": "PK", "status": "Open", "rating": 4.5, "reviews": 50,
            "website": "x.pk"}
    assert searches.passes(good, options)
    assert not searches.passes({**good, "country_code": "IN"}, options)
    assert not searches.passes({**good, "status": "Permanently closed"}, options)
    assert not searches.passes({**good, "rating": 3.9}, options)
    assert not searches.passes({**good, "reviews": 9}, options)
    assert not searches.passes({**good, "website": ""}, options)
    assert not searches.passes({**good, "rating": None}, options)


# --- storage ----------------------------------------------------------------
def test_save_dedupes_and_resumes(fresh_db):
    first = searches.create({"niches": ["cafe"], "countries": ["Pakistan"]})
    lead = {"place_id": "A", "name": "One"}
    assert searches.save_leads(first, [lead, lead, {"place_id": "B", "name": "Two"}]) == [
        lead, {"place_id": "B", "name": "Two"}]
    assert searches.save_leads(first, [lead]) == []
    assert searches.count(first) == 2

    second = searches.create({"niches": ["cafe"], "countries": ["Pakistan"]})
    assert searches.save_leads(second, [lead], skip_known=True) == []
    assert searches.save_leads(second, [lead]) == [lead]

    searches.mark_query_done(first, "cafe in Lahore, Pakistan")
    searches.mark_query_done(first, "cafe in Lahore, Pakistan")
    assert searches.get(first)["progress"]["done"] == ["cafe in Lahore, Pakistan"]

    searches.update_lead(first, "A", {"emails": "hi@one.pk"})
    assert searches.leads(first)[0] == {"place_id": "A", "name": "One", "emails": "hi@one.pk",
                                        "found": db.now()[:10]}


def test_minimum_keeps_every_match_the_website_check_leaves(fresh_db, monkeypatch):
    """Leads the age requirement drops do not count, and every match found is kept."""
    from app.core import enrich
    from app.workers import scrape

    def fake_search(client, query, cancelled):
        for start in range(0, 100, 20):
            yield [{"place_id": f"{query}-{n}", "status": "Open", "country_code": "PK",
                    "website": "x.pk"} for n in range(start, start + 20)]

    class FakeEnricher:
        def __init__(self, wayback):
            pass

        def enrich(self, lead, find_contacts, find_owner=False):
            young = int(lead["place_id"].rsplit("-", 1)[1]) % 2 == 0
            return {"enriched": True, "young": young, "age_years": 1 if young else 5}

        def close(self):
            pass

    monkeypatch.setattr(scrape.scraper, "search", fake_search)
    monkeypatch.setattr(scrape.scraper, "MapsClient", lambda: FakeEnricher(False))
    monkeypatch.setattr(enrich, "Enricher", FakeEnricher)
    # Saved the way 0.2 did: "startup" and "Stop after" become an age range and a minimum
    search_id = searches.create({"niches": ["cafe"], "countries": ["Pakistan"],
                                 "cities": ["Lahore, Pakistan"], "company_age": "startup",
                                 "find_emails": False, "max_results": 30})
    options = searches.get(search_id)["options"]
    assert (options["age_min"], options["age_max"], options["min_leads"]) == (0, 2, 30)
    result = scrape.ScrapeWorker(search_id).work()
    assert result["status"] == "done" and searches.count(search_id) == 50
    assert all(lead["young"] for lead in searches.leads(search_id))
    assert result["dropped"] == {"older than 2 years": 50}

    # Stop does not wait for website checks already under way
    import threading
    import time

    started = threading.Event()
    FakeEnricher.enrich = lambda self, lead, contacts, **_: (started.set(), time.sleep(3), {})[2]
    worker = scrape.ScrapeWorker(searches.create({**searches.get(search_id)["options"],
                                                  "min_leads": 0}))
    threading.Thread(target=lambda: (started.wait(), worker.stop()), daemon=True).start()
    began = time.monotonic()
    assert worker.work()["status"] == "stopped"
    assert time.monotonic() - began < 2


def test_short_searches_dig_deeper_into_the_city(fresh_db, monkeypatch):
    """Google stops at about 120 per search; the city is then searched again in map views."""
    from app.workers import scrape

    def fake_search(client, query, cancelled):
        if "@" in query:  # a map view: 10 more, all with a phone
            cell = query.rsplit("@", 1)[1]
            yield [{"place_id": f"{cell}-{n}", "status": "Open", "country_code": "AE",
                    "query": query.split(" @")[0], "phone": "1", "reviews": n}
                   for n in range(10)]
            return
        for start in range(0, 120, 20):
            yield [{"place_id": f"city-{n}", "status": "Open", "country_code": "AE",
                    "query": query, "phone": "1" if n % 3 else "", "reviews": n,
                    "latitude": 25.2 + (n % 11) / 200, "longitude": 55.27 + (n % 7) / 200}
                   for n in range(start, start + 20)]

    monkeypatch.setattr(scrape.scraper, "search", fake_search)
    monkeypatch.setattr(scrape.scraper, "MapsClient",
                        lambda: type("C", (), {"close": lambda self: None})())
    search_id = searches.create({
        "niches": ["cafe"], "countries": ["United Arab Emirates"],
        "cities": ["Dubai, United Arab Emirates"], "find_emails": False,
        "require_phone": True, "min_leads": 100})
    result = scrape.ScrapeWorker(search_id).work()
    deep = searches.get(search_id)["progress"]["deep"]
    assert deep and all(q.startswith("cafe near Dubai, United Arab Emirates @") for q in deep)
    assert result["status"] == "done" and result["found"] == 80 + 10 * len(deep) >= 100
    assert result["dropped"] == {"no phone number": 40}
    kept = searches.leads(search_id)
    assert [lead["quality"] for lead in kept] == sorted((lead["quality"] for lead in kept),
                                                        reverse=True)  # best first

    # Leads the user deletes are not picked again when the search is resumed
    searches.delete_leads([kept[0]["place_id"]], search_id)
    scrape.ScrapeWorker(search_id).work()
    assert searches.count(search_id) == len(kept) - 1
    assert searches.dropped_counts(search_id)[searches.REMOVED] == 1


def test_website_requirements_and_use_cases():
    options = searches.options_with_defaults({"age_min": 3, "require_email": True,
                                              "require_linkedin": True})
    lead = {"age_years": 5, "emails": "a@x.com", "linkedin": "https://linkedin.com/company/x"}
    assert searches.why_not_checked(lead, options) is None
    assert searches.why_not_checked({**lead, "age_years": 2}, options) == "younger than 3 years"
    assert searches.why_not_checked({**lead, "age_years": None}, options) is None  # unknown kept
    assert searches.why_not_checked({**lead, "emails": ""}, options) == "no email found"
    assert searches.why_not_checked({**lead, "linkedin": places.NOT_FOUND},
                                    options) == "no LinkedIn found"
    assert searches.is_age_reason("younger than 3 years")
    assert searches.visits_websites({**searches.DEFAULT_OPTIONS, "find_emails": False,
                                     "require_owner": True})
    assert not searches.passes({"status": "Open", "claimed": "No"},
                               searches.options_with_defaults({"require_claimed": True}))
    # Each quick setup sets every requirement, so they never mix
    assert {frozenset(case) for case in searches.USE_CASES.values()} == {
        frozenset(searches.USE_CASES["email"])}
    assert searches.related_types(["Dentist", "dental clinic"]) == ["orthodontist",
                                                                    "cosmetic dentist"]


def test_quality_score():
    bare = {"place_id": "a"}
    full = {"phone": "1", "website": "x", "emails": "a@x", "rating": 4.6, "reviews": 1000,
            "claimed": "Yes", "address": "1 Road", "hours": "Mon: 9-5", "facebook": "https://f",
            "instagram": "https://i", "linkedin": "https://l", "owner_name": "A B",
            "age_years": 4, "description": "Clinic"}
    assert searches.quality(bare) == 0 and searches.quality(full) == 100
    assert searches.quality({**full, "linkedin": places.NOT_FOUND}) == 94
    assert searches.quality({"address": places.SERVICE_AREA}) == 0
    assert sum(most for _what, _points, most in searches.quality_parts(bare)) == 100
    assert searches.score({"quality": 60, "ai_score": 80}) == 70


def test_hidden_address_takes_the_searched_city():
    view = [5000, 55.27, 25.2]  # Dubai, as Google centres the map: distance, lng, lat
    near = {"address": places.SERVICE_AREA, "city": "", "country_code": "", "status": "Open",
            "latitude": 25.1, "longitude": 55.2}
    scraper.near_place(near, "cafe in Dubai, United Arab Emirates", view)
    assert near["city"] == "Dubai" and near["country_code"] == "AE"
    far = {**near, "city": "", "country_code": "", "latitude": 49.2}  # a pin in Europe
    scraper.near_place(far, "cafe in Dubai, United Arab Emirates", view)
    assert far["country_code"] == ""
    options = searches.options_with_defaults({"countries": ["United Arab Emirates"]})
    assert searches.why_not(near, options) is None
    assert searches.why_not(far, options) == "outside the chosen countries"
    assert searches.why_not(near, {**options, "require_address": True}) == "address hidden"


# --- export -----------------------------------------------------------------
def test_export_xlsx_and_csv(tmp_path):
    from openpyxl import load_workbook

    from app.core import exporter

    leads = [
        {"name": "=HYPERLINK(\"http://evil\")", "phone": "+92 300 1234567", "rating": 4.5,
         "website": "https://a.pk", "reviews": 10, "description": "bad\x01char"},
        {"name": "B", "phone": "", "rating": None, "website": "", "reviews": 0},
    ]
    assert [k for k, _ in exporter.columns_in_use(leads)] == [
        "name", "phone", "website", "rating", "reviews", "description"]

    exporter.export(leads, tmp_path / "out.xlsx")
    sheet = load_workbook(tmp_path / "out.xlsx").active
    assert sheet["A1"].value == "Name"
    assert sheet["A2"].value == "=HYPERLINK(\"http://evil\")" and sheet["A2"].data_type == "s"
    assert sheet["D2"].value == 4.5
    assert sheet["C2"].hyperlink.target == "https://a.pk"
    assert sheet["F2"].value == "badchar"

    exporter.export(leads, tmp_path / "out.csv")
    text = (tmp_path / "out.csv").read_text("utf-8-sig")
    assert "'=HYPERLINK" in text and ",+92 300 1234567," in text
    assert exporter.safe_csv("-cmd|' /C calc'!A0").startswith("'")

    # Only the columns the user kept on screen
    exporter.export(leads, tmp_path / "some.csv", keys=["name", "rating", "email"])
    assert (tmp_path / "some.csv").read_text("utf-8-sig").splitlines()[0] == "Name,Rating"


def test_delete_leads_from_one_search_or_all(fresh_db):
    first, second = searches.create({"niches": ["cafe"]}), searches.create({"niches": ["cafe"]})
    for search_id in (first, second):
        searches.save_leads(search_id, [{"place_id": "a", "name": "A"},
                                        {"place_id": "b", "name": "B"}])
    searches.delete_leads(["a"], first)
    assert [lead["place_id"] for lead in searches.leads(first)] == ["b"]
    assert len(searches.leads(second)) == 2
    searches.delete_leads(["b"])
    assert [lead["place_id"] for lead in searches.leads(second)] == ["a"]
    assert searches.leads(first) == []
    assert searches.get(first)["options"]["fields"][0] == "name"  # default: every column


# --- enrichment -------------------------------------------------------------
def test_find_emails_handles_obfuscation_and_junk():
    from app.core import enrich

    # Cloudflare encodes "info@acme.pk" with key 0x42
    hidden = "42" + "".join(f"{ord(c) ^ 0x42:02x}" for c in "info@acme.pk")
    page = ('<a href="mailto:Sales@Acme.pk">x</a> logo@2x.png you@example.com '
            f'hello&#64;acme.pk mailto:%20sales@acme.pk hello@acme.pkClifton gebruiker@domein.com max@mustermann.de a@sentry.wixpress.com <span data-cfemail="{hidden}"></span> sales@acme.pk')
    assert enrich.find_emails(page) == ["sales@acme.pk", "hello@acme.pk", "info@acme.pk"]


def test_find_socials_skips_share_buttons():
    from app.core import enrich

    page = ('<a href="https://www.facebook.com/sharer/sharer.php?u=x"></a>'
            '<a href="https://www.facebook.com/AcmeDental/">fb</a>'
            '<a href="//instagram.com/acme.dental">ig</a>'
            '<a href="https://twitter.com/intent/tweet">t</a><a href="https://x.com/acme">x</a>'
            '<a href="https://www.linkedin.com/company/acme-dental">li</a>')
    assert enrich.find_socials(page) == {
        "facebook": "https://www.facebook.com/AcmeDental",
        "instagram": "https://instagram.com/acme.dental",
        "linkedin": "https://www.linkedin.com/company/acme-dental",
        "twitter": "https://x.com/acme",
    }


def test_linkedin_from_the_website():
    from app.core import enrich

    page = ('<a href="https://ae.linkedin.com/in/omar-farsi-123/">Omar</a>'
            '<a href="//www.linkedin.com/in/jane-doe">Jane</a>'
            '<a href="https://www.linkedin.com/company/acme">Acme</a>')
    profiles = enrich.find_profiles(page)
    assert profiles == ["https://ae.linkedin.com/in/omar-farsi-123",
                        "https://www.linkedin.com/in/jane-doe"]
    assert enrich.find_socials(page)["linkedin"] == "https://www.linkedin.com/company/acme"
    assert enrich.owner_profile(profiles, "Omar Farsi") == profiles[0]
    assert enrich.owner_profile(profiles, None) == "N/A"  # two people, no name to tell them apart
    assert enrich.owner_profile(profiles[1:], None) == profiles[1]
    assert enrich.owner_profile([], "Omar Farsi") == "N/A"


def test_company_age():
    from datetime import date

    from app.core import enrich

    rdap = {"events": [{"eventAction": "expiration", "eventDate": "2030-01-01T00:00:00Z"},
                       {"eventAction": "registration", "eventDate": "2024-05-01T10:00:00Z"}]}
    created = enrich.registration_date(rdap)
    fields = enrich.age_fields(created, today=date(2026, 10, 16))
    assert fields == {"domain_created": "2024-05-01", "company_age": "Startup (2 years)",
                      "age_years": 2, "age_source": "Domain registration"}
    young = enrich.age_fields(date(2026, 3, 1), today=date(2026, 10, 16))
    assert young["company_age"] == "Startup (under 1 year)"
    assert enrich.domain_candidates("clinic.netlify.app") == []
    assert enrich.domain_candidates("www.shop.acme.co.uk") == ["shop.acme.co.uk", "acme.co.uk",
                                                               "co.uk"]


def test_enrich_crawls_contact_page_and_looks_up_age():
    from datetime import date

    import httpx

    from app.core import enrich

    pages = {
        "https://acme.pk/": '<a href="/contact-us">Contact</a><a href="https://other.com/contact">',
        "https://acme.pk/contact-us": "Write to info@acme.pk or acme@gmail.com",
    }

    def handler(request):
        url = str(request.url)
        if url.startswith("https://rdap.org/domain/old.pk"):
            return httpx.Response(404)
        if url.startswith("https://web.archive.org/cdx"):
            return httpx.Response(200, json=[["timestamp"], ["20120304050607"]])
        if url.startswith("https://rdap.org/domain/acme.pk"):
            return httpx.Response(200, json={"events": [
                {"eventAction": "registration", "eventDate": "2010-01-01T00:00:00Z"}]})
        if url in pages:
            return httpx.Response(200, text=pages[url], headers={"content-type": "text/html"})
        return httpx.Response(404)

    enricher = enrich.Enricher(transport=httpx.MockTransport(handler))
    fields = enricher.enrich({"website": "https://acme.pk/", "domain": "acme.pk"})
    assert fields["emails"] == "info@acme.pk, acme@gmail.com"
    assert fields["company_age"].startswith("Established") and fields["enriched"]

    assert enricher.domain_created("old.pk") == (
        date(2012, 3, 4), "First seen online (Wayback Machine)")

    social = enricher.enrich({"website": "https://www.facebook.com/acme"})
    assert social == {"enriched": True, "facebook": "https://www.facebook.com/acme"}


# --- smart mode -------------------------------------------------------------
def test_ai_prompt_and_reply_parsing():
    from app.core import ai

    leads = [{"place_id": "A", "name": "One", "emails": "a@b.c", "instagram": "x", "hours": "h" * 900},
             {"place_id": "B", "name": "Two"}]
    prompt = ai.build_prompt("Clinics with a website", "dentist in Lahore", leads)
    assert '"id": 0' in prompt and '"has_email": true' in prompt and '"instagram"' in prompt
    assert "h" * 301 not in prompt  # long fields are cut down

    reply = 'Sure!\n```json\n{"results": [{"id": 0, "score": 140, "reason": "Great"},' \
            '{"id": 1, "score": 30, "reason": "Closed"}, {"id": 7, "score": 90, "reason": "?"},' \
            '{"id": "x"}]}\n```'
    assert ai.parse_reply(reply, leads) == {
        "A": {"ai_score": 100, "ai_verdict": "Good fit", "ai_reason": "Great"},
        "B": {"ai_score": 30, "ai_verdict": "Poor fit", "ai_reason": "Closed"},
    }
    assert ai.verdict(50) == "Maybe" and ai.verdict(49) == "Poor fit"
    with pytest.raises(ai.AIError):
        ai.parse_reply("no json here", leads)


def test_ai_openai_style_call_retries_rate_limits(monkeypatch):
    import httpx

    from app.core import ai

    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((url, headers, json["model"]))
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        content = '{"results": [{"id": 0, "score": 85, "reason": "Fits"}]}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(ai.httpx, "post", fake_post)
    monkeypatch.setattr(ai.time, "sleep", lambda seconds: None)
    cfg = {"kind": "openai", "base_url": "https://api.groq.com/openai/v1", "model": "m",
           "key": "k", "profile": ""}
    assert ai.test(cfg) == {"ai_score": 85, "ai_verdict": "Good fit", "ai_reason": "Fits"}
    assert len(calls) == 2
    assert calls[0][0].endswith("/chat/completions") and calls[0][1] == {"Authorization": "Bearer k"}


def test_ai_wrong_key_is_fatal(monkeypatch):
    import httpx

    from app.core import ai

    monkeypatch.setattr(ai.httpx, "post", lambda *a, **k: httpx.Response(401))
    cfg = {"kind": "gemini", "base_url": "https://x", "model": "m", "key": "bad", "profile": ""}
    with pytest.raises(ai.AIError) as caught:
        ai.score(cfg, "q", [{"place_id": "A", "name": "One"}])
    assert caught.value.fatal
    with pytest.raises(ai.AIError):
        ai.score({**cfg, "key": ""}, "q", [])


# --- updates ----------------------------------------------------------------
def test_update_version_and_release_parsing(tmp_path):
    from pathlib import Path

    from app.services import updater

    assert updater.is_newer("v0.2.0", "v0.1.0 beta")
    # the tag is written with or without "beta": the same numbers are never an update
    assert not updater.is_newer("v0.1.1", "v0.1.1 beta")
    assert not updater.is_newer("v0.1.0-beta", "v0.1.0 beta")
    assert not updater.is_newer("v0.0.9", "v0.1.0 beta")
    release = updater.parse_release({
        "tag_name": "v0.2.0", "html_url": "https://github.com/x/releases/v0.2.0", "body": "Notes",
        "assets": [{"name": "source.zip"},
                   {"name": "GeoHarvest-v0.2.0-windows.zip", "size": 10,
                    "browser_download_url": "https://dl/zip", "digest": "sha256:ABC"}]})
    assert (release.zip_url, release.sha256, release.zip_size) == ("https://dl/zip", "abc", 10)
    assert updater.update_command(Path("C:/tmp/GeoHarvest-Setup.exe"), Path("C:/Apps/GeoHarvest")) == [
        str(Path("C:/tmp/GeoHarvest-Setup.exe")), "--update", "--target", str(Path("C:/Apps/GeoHarvest"))]

    # Setup (standard library only) reads releases the same way, to install the newest
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "installer"))
    import setup_app

    assert setup_app.parse_latest({"tag_name": "v0.2.0", "assets": [
        {"name": "GeoHarvest-v0.2.0-windows.zip", "size": 10, "browser_download_url": "https://dl/zip",
         "digest": "sha256:ABC"}]}) == {"tag": "v0.2.0", "url": "https://dl/zip", "size": 10,
                                        "sha256": "abc"}
    assert setup_app.parse_latest({"tag_name": "v0.2.0", "assets": []}) is None
    assert setup_app.version_tuple("v0.3.0-beta") > setup_app.version_tuple("v0.2.2 beta")


# --- 0.2.1 filters, area search, owner ---------------------------------------
def test_opening_hours():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.core import hours

    text = "Monday: 1-11 PM; Tuesday: 9 AM-12 AM; Wednesday: 6 PM-2 AM; Thursday: Closed; " \
           "Friday: 9 AM-1 PM, 3-7 PM; Saturday: Open 24 hours; Sunday: Closed"
    week = hours.weekly(text)
    assert week[0] == [(13 * 60, 23 * 60)]
    assert week[1] == [(9 * 60, 24 * 60)] and week[3] == []
    assert hours.open_at(text, 3, 60)                  # Wednesday's late night runs into Thursday
    assert not hours.open_at(text, 3, 3 * 60)
    assert hours.open_at(text, 4, 16 * 60) and not hours.open_at(text, 4, 14 * 60)
    assert hours.open_weekends(text) and not hours.always_open(text)
    every_day = "; ".join(f"{day}: Open 24 hours" for day in hours.DAYS)
    assert hours.always_open(every_day)
    monday_2pm_dubai = datetime(2026, 10, 19, 14, 0, tzinfo=ZoneInfo("Asia/Dubai"))
    assert hours.open_now(text, "Asia/Dubai", monday_2pm_dubai)
    assert not hours.open_now(text, "Asia/Karachi", monday_2pm_dubai.replace(hour=11))


def test_new_filters():
    def keep(lead, **options):
        return searches.passes(lead, searches.options_with_defaults(
            {"skip_closed": False, **options}))

    lead = {"rating": 4.6, "reviews": 3, "website": "", "hours": "Monday: 9 AM-5 PM"}
    assert keep(lead, max_rating=4.8) and not keep(lead, max_rating=4.5)
    assert keep(lead, max_reviews=3) and not keep(lead, max_reviews=2)
    assert keep(lead, max_reviews=-1)
    assert keep(lead, website="no") and not keep(lead, website="yes")
    assert keep(lead, open_at=True, open_day=0, open_time="10:30")
    assert not keep(lead, open_at=True, open_day=1, open_time="10:30")
    assert not keep({**lead, "hours": ""}, open_weekends=True)  # unknown hours are left out
    # Searches saved before 0.2.1
    assert searches.options_with_defaults({"require_website": True})["website"] == "yes"


def test_area_search_queries_and_circle():
    from app.core import geo

    options = {"niches": ["dentist"], "where": "area", "area_place": "Dubai Marina",
               "area_km": 3, "area_lat": 25.08, "area_lng": 55.13}
    queries = searches.build_queries(options)
    assert len(queries) == 4 and all(q.startswith("dentist near Dubai Marina @") for q in queries)
    match = scraper.AREA.match(queries[0])
    assert match and match.group(1) == "dentist near Dubai Marina"
    assert searches.title(options) == "dentist within 3 km of Dubai Marina"
    full = searches.options_with_defaults({**options, "skip_closed": False})
    assert searches.passes({"latitude": 25.09, "longitude": 55.14}, full)
    assert not searches.passes({"latitude": 25.2, "longitude": 55.13}, full)  # 13 km away
    assert 13 < geo.distance_km(25.08, 55.13, 25.2, 55.13) < 14
    # The plan on the form counts the same before the place is found on the map
    assert len(searches.build_queries({**options, "area_lat": None})) == 4


def test_owner_name():
    from app.core import enrich

    assert enrich.find_owner("<p>Founder: Jane Smith</p>") == "Jane Smith"
    assert enrich.find_owner("<div>Jane Smith, Owner of Acme</div>") == "Jane Smith"
    assert enrich.find_owner("<p>Acme was founded in 2012 by Omar Farsi.</p>") == "Omar Farsi"
    assert enrich.find_owner("<h3>Dr. Udita Baralay</h3> Co-Founder") == "Dr. Udita Baralay"
    assert enrich.find_owner('{"founder": {"@type": "Person", "name": "Lena Weber"}}') == \
        "Lena Weber"
    assert enrich.find_owner("<h2>Meet Our Team</h2><p>Contact our owner today!</p>") is None
    hidden = {"entities": [{"roles": ["registrant"], "vcardArray": [
        "vcard", [["fn", {}, "text", "REDACTED FOR PRIVACY"]]]}]}
    shown = {"entities": [{"roles": ["registrant"], "vcardArray": [
        "vcard", [["version", {}, "text", "4.0"], ["fn", {}, "text", "Ahmed Khan"]]]}]}
    assert enrich.registrant(hidden) is None and enrich.registrant(shown) == "Ahmed Khan"


def test_crm_and_sheets_export(tmp_path):
    import csv

    from app.core import exporter

    leads = [{"name": "=Acme", "emails": "a@acme.ae, b@acme.ae", "phone": "+971 4 555 0100",
              "address": "1 Marina Walk, Dubai", "city": "Dubai", "description": "line\tone\ntwo"}]
    for crm in set(exporter.CRMS) - exporter.ONE_ROW_PER_EMAIL:
        exporter.to_crm(leads, tmp_path / f"{crm}.csv", crm)
        rows = list(csv.reader((tmp_path / f"{crm}.csv").open(encoding="utf-8-sig")))
        assert len(rows) == 2 and rows[1][0] == "'=Acme"  # never a formula
        assert "a@acme.ae" in rows[1] and "b@acme.ae, " not in rows[1]
    # HomingPigeon: one row per email, in the columns its import recognises
    assert exporter.to_crm(leads + [{"name": "No email"}], tmp_path / "hp.csv", "homingpigeon") == 2
    rows = list(csv.reader((tmp_path / "hp.csv").open(encoding="utf-8-sig")))
    assert rows[0][:3] == ["Email", "Company", "Contact person"]
    assert [r[:2] for r in rows[1:]] == [["a@acme.ae", "'=Acme"], ["b@acme.ae", "'=Acme"]]
    hubspot = dict(zip(*csv.reader((tmp_path / "hubspot.csv").open(encoding="utf-8-sig"))))
    assert hubspot["Street address"] == "1 Marina Walk, Dubai"  # no street part: whole address
    text = exporter.to_tsv(leads, ["name", "phone", "description"])
    assert text.splitlines() == ["Name\tPhone\tDescription",
                                 "'=Acme\t'+971 4 555 0100\tline one two"]


def test_backup_restore_and_weekly(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    from app import config
    from app.core import backup

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    first = searches.create({"niches": ["cafe"]})
    saved = backup.write_backup(tmp_path / "mine.ghbackup")
    assert backup.is_backup(saved) and not backup.is_backup(tmp_path / "nothing.ghbackup")
    searches.delete(first)
    safety = backup.restore_backup(saved)
    assert searches.get(first)["options"]["niches"] == ["cafe"]  # back again
    assert backup.is_backup(safety)  # what was there before is kept
    # Weekly: once per 7 days, the newest 4 kept
    start = datetime(2026, 1, 1)
    made = [backup.auto_backup(start + timedelta(days=day)) for day in range(0, 60, 3)]
    assert sum(1 for path in made if path) == 7  # days 0, 9, 18 ... 54
    assert len(list(backup.folder().glob(f"{backup.AUTO_NAME} *"))) == backup.AUTO_KEEP
    db.set_setting("auto_backup", False)
    assert backup.auto_backup(start + timedelta(days=400)) is None


def test_presets_and_estimate():
    options = searches.options_with_defaults({"niches": ["gym"], "cities": ["Oslo, Norway"],
                                              "require_email": True, "min_leads": 50})
    searches.save_preset("Cold email", options)
    preset = searches.presets()["Cold email"]
    assert preset["require_email"] and preset["min_leads"] == 50
    assert not set(searches.PRESET_SKIPS) & set(preset)  # never the types or places
    searches.save_preset("Calls", options)
    searches.save_preset("Cold email", options)  # saving again moves it to the end
    assert list(searches.presets()) == ["Calls", "Cold email"]
    searches.delete_preset("Calls")
    assert list(searches.presets()) == ["Cold email"]
    listed, low, high = searches.estimate(10, 4, visit_websites=True)
    assert listed == 1200 and 1 <= low <= high
    assert searches.estimate(10, 4, False)[2] < high  # website visits take longer


def test_found_exported_and_show_filters():
    from app.ui.widgets.leads_model import SHOW_MENU, SHOWS, SORT_MENU, SORTS

    one, two = searches.create({"niches": ["cafe"]}), searches.create({"niches": ["bar"]})
    lead = {"place_id": "X", "name": "X", "emails": "x@x.pk", "website": "https://x.pk",
            "age_years": 1}
    searches.save_leads(one, [lead])
    searches.save_leads(two, [lead, {"place_id": "Y", "name": "Y", "age_years": 9}])
    searches.mark_exported(["X"], "2026-10-01")
    assert [item["exported"] for item in searches.leads(two) if "exported" in item] == ["2026-10-01"]
    assert searches.leads(one)[0]["exported"] == "2026-10-01"  # every search that has it
    x, y = searches.leads(two)
    assert x["found"] == db.now()[:10]
    picked = {key for key, test in SHOWS.items() if test(x)}
    assert picked == {"all", "email", "website", "startup"}
    assert {key for key, test in SHOWS.items() if test(y)} == {"all", "no_website", "established",
                                                               "new"}
    # every menu entry has a rule, and every rule a menu entry
    assert {e[0] for e in SHOW_MENU if e} == set(SHOWS)
    assert {e[0] for e in SORT_MENU if e} == set(SORTS)


def test_proxies_parse_and_rotate(page):
    import httpx

    good, bad = scraper.parse_proxies(
        "1.2.3.4:8080\nuser:pw@5.6.7.8:3128\nsocks5://9.9.9.9:1080\n"
        "10.0.0.1:8000:bob:secret\n# a comment\nnot a proxy\n\n")
    assert good == ["http://1.2.3.4:8080", "http://user:pw@5.6.7.8:3128",
                    "socks5://9.9.9.9:1080", "http://bob:secret@10.0.0.1:8000"]
    assert bad == ["not a proxy"]

    body = ")]}'\n" + json.dumps(page)

    class Fake:
        def __init__(self, answer):
            self.answer, self.calls = answer, 0

        def get(self, url, params):
            self.calls += 1
            if self.answer == "dead":
                raise httpx.ConnectError("no answer")
            request = httpx.Request("GET", url)
            if self.answer == "limited":
                return httpx.Response(429, request=request)
            return httpx.Response(200, text=body, request=request)

    client = scraper.MapsClient(proxies=[])
    client.clients = [Fake("dead"), Fake("limited"), Fake("ok")]
    for _ in range(3):  # whichever proxy's turn it is, the working one answers
        assert client.fetch("dentist in Lahore")
    assert client.clients[2].calls == 3
    client.clients = [Fake("limited"), Fake("dead")]
    with pytest.raises(scraper.Blocked):  # every proxy limited or dead: pause the search
        client.fetch("dentist in Lahore")


def test_every_column_has_a_group():
    keys = [key for _group, group_keys in places.FIELD_GROUPS for key in group_keys]
    assert sorted(keys) == sorted(key for key, _ in places.FIELDS) and len(keys) == len(set(keys))


# --- 0.3 appearance ---------------------------------------------------------
def test_theme_files_and_menu_order(fresh_db, tmp_path):
    from app.core import prefs, themes

    spec = themes.save_custom({**themes.PRESETS["ocean"], "name": "Mine"})
    saved = themes.write_file(tmp_path / "mine.txt", spec)
    assert saved.suffix == ".ghtheme" and themes.read_file(saved) == spec
    # HomingPigeon's theme files load too
    other = tmp_path / "hp.hptheme"
    other.write_text(json.dumps({"homingpigeon_theme": 1, **spec}), encoding="utf-8")
    assert themes.read_file(other)["name"] == "Mine"
    other.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        themes.read_file(other)
    assert themes.find(themes.custom_key("mine"))["accent"] == spec["accent"]
    assert prefs.ordered(["a", "b", "c"], ["c", "gone", "a"]) == ["c", "a", "b"]
    db.set_setting("nav_hidden", ["search", "smart"])
    assert prefs.hidden_pages() == {"smart"}  # New search can never be hidden
