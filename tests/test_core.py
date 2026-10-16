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
    chosen = {"niches": ["dentist", " "], "country": "Pakistan", "cities": ["Lahore", "Multan"]}
    assert searches.build_queries(chosen) == [
        "dentist in Lahore, Pakistan", "dentist in Multan, Pakistan"]
    sweep = searches.build_queries({"niches": ["cafe", "bakery"], "country": "Pakistan",
                                    "city_count": 2})
    assert sweep == ["cafe in Lahore, Pakistan", "bakery in Lahore, Pakistan",
                     "cafe in Karachi, Pakistan", "bakery in Karachi, Pakistan"]
    assert searches.title({"niches": ["cafe"], "country": "Pakistan", "city_count": 2}) == \
        "cafe in Pakistan (2 biggest cities)"


def test_filters():
    options = searches.options_with_defaults(
        {"country": "Pakistan", "min_rating": 4, "min_reviews": 10, "require_website": True})
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
    first = searches.create({"niches": ["cafe"], "country": "Pakistan"})
    lead = {"place_id": "A", "name": "One"}
    assert searches.save_leads(first, [lead, lead, {"place_id": "B", "name": "Two"}]) == [
        lead, {"place_id": "B", "name": "Two"}]
    assert searches.save_leads(first, [lead]) == []
    assert searches.count(first) == 2

    second = searches.create({"niches": ["cafe"], "country": "Pakistan"})
    assert searches.save_leads(second, [lead], skip_known=True) == []
    assert searches.save_leads(second, [lead]) == [lead]

    searches.mark_query_done(first, "cafe in Lahore, Pakistan")
    searches.mark_query_done(first, "cafe in Lahore, Pakistan")
    assert searches.get(first)["progress"]["done"] == ["cafe in Lahore, Pakistan"]

    searches.update_lead(first, "A", {"emails": "hi@one.pk"})
    assert searches.leads(first)[0] == {"place_id": "A", "name": "One", "emails": "hi@one.pk"}


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


# --- enrichment -------------------------------------------------------------
def test_find_emails_handles_obfuscation_and_junk():
    from app.core import enrich

    # Cloudflare encodes "info@acme.pk" with key 0x42
    hidden = "42" + "".join(f"{ord(c) ^ 0x42:02x}" for c in "info@acme.pk")
    page = ('<a href="mailto:Sales@Acme.pk">x</a> logo@2x.png you@example.com '
            f'hello&#64;acme.pk mailto:%20sales@acme.pk hello@acme.pkClifton <span data-cfemail="{hidden}"></span> sales@acme.pk')
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
    assert enrich.matches_age(fields, "startup") and not enrich.matches_age(fields, "established")
    assert enrich.matches_age({}, "any") and not enrich.matches_age({}, "startup")
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
