"""Extra detail from each business's own website: emails, social links, company age.

For each lead with a website we read the home page and up to three contact or
about pages linked from it, and look up when the domain was registered (RDAP,
the free public successor to WHOIS). Google Maps has no founding date, so the
domain's age is the best free estimate of how old a company is. Some country
registries (.pk, for one) publish no dates over RDAP; for those the first
snapshot in the Internet Archive's Wayback Machine stands in.

When the user asks for it, the same pages are read for the owner's name ("Founder: Jane
Smith", "Jane Smith, Owner", or the page's schema.org data), and the domain record for a
registrant name that is not hidden for privacy. LinkedIn blocks automatic reading, so the
lead gets a LinkedIn search link to check by hand instead.
"""
from __future__ import annotations

import html
import re
import threading
from datetime import date, datetime
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from app.core.places import NOT_FOUND
from app.core.scraper import USER_AGENT

STARTUP_YEARS = 3
MAX_PAGES = 4
MAX_BYTES = 2_000_000
MAX_EMAILS = 5
SITE_TEXT = 1200  # characters of the home page Smart mode may read

SOCIAL = {
    "facebook": re.compile(
        r"(?:https?:)?//(?:www\.|m\.|web\.)?facebook\.com/"
        r"(?!sharer|share|plugins|dialog|tr[/?]|login|groups/?$)[\w.\-/?=%]+", re.I),
    "instagram": re.compile(r"(?:https?:)?//(?:www\.)?instagram\.com/(?!p/|explore|accounts)[\w.]+",
                            re.I),
    "linkedin": re.compile(r"(?:https?:)?//(?:[a-z]{2,3}\.)?linkedin\.com/(?:company|school)/"
                           r"[\w\-%.]+", re.I),
    "twitter": re.compile(r"(?:https?:)?//(?:www\.)?(?:twitter|x)\.com/"
                          r"(?!intent|share|home|search|hashtag)\w+", re.I),
    "youtube": re.compile(r"(?:https?:)?//(?:www\.)?youtube\.com/(?:channel/|c/|user/|@)[\w\-.]+",
                          re.I),
    "tiktok": re.compile(r"(?:https?:)?//(?:www\.)?tiktok\.com/@[\w.]+", re.I),
}
# A person's profile, as a small business often links its owner's or its team's
PROFILE = re.compile(r"(?:https?:)?//(?:[a-z]{2,3}\.)?linkedin\.com/in/[\w\-%.]+", re.I)
# Starts only where a run of address characters starts, and an address's name part is at
# most 64 long: without both, a long run with no "@" (a picture inside a page) took
# minutes and froze the app
EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}"
                   r"@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,24}")
CFEMAIL = re.compile(r'data-cfemail="([0-9a-fA-F]+)"')
HREF = re.compile(r'href\s*=\s*["\']([^"\'#]+)', re.I)
CONTACT_WORDS = ("contact", "about", "impressum", "kontakt", "contacto", "contato", "team",
                 "get-in-touch", "reach-us", "nous-contacter", "founder", "leadership",
                 "our-story", "who-we-are")
NOT_EMAIL_ENDINGS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js", ".ico")
# Free website builders: the domain's age is the platform's, not the business's
HOSTED_SUFFIXES = ("netlify.app", "vercel.app", "github.io", "wixsite.com", "wix.com",
                   "blogspot.com", "wordpress.com", "business.site", "square.site", "webflow.io",
                   "godaddysites.com", "weebly.com", "carrd.co", "linktr.ee", "sites.google.com",
                   "google.com", "jimdosite.com", "myshopify.com", "pages.dev", "web.app",
                   "firebaseapp.com", "herokuapp.com", "site123.me", "strikingly.com", "cal.com")
WAYBACK_AT_ONCE = 4  # the archive is slow and shared; be gentle with it
# Template addresses left in contact forms ("you@example.com"), in the languages GeoHarvest
# is used in most. Matched exactly or as whole names, so a real "mycompany.com" survives.
PLACEHOLDER_DOMAINS = {"domain.com", "email.com", "company.com", "website.com", "mysite.com",
                       "test.com", "yourdomain.com", "yoursite.com", "wixpress.com",
                       "godaddy.com", "sentry.io"}
PLACEHOLDER_NAMES = ("example", "domein", "beispiel", "exemple", "ejemplo", "dominio", "esempio",
                     "voorbeeld", "musterfirma", "mustermann", "votredomaine", "tudominio",
                     "ihredomain", "sentry")


# Owner's name: a role word next to a name of two or three capitalised words
ROLE = (r"(?i:co-?founder|founder|owner|proprietor|ceo|chief executive officer|managing director|"
        r"managing partner|principal|president|geschäftsführer(?:in)?|inhaber(?:in)?|gérant|"
        r"fondateur|fondatrice|propietario|propietaria|director general)")
NAME = r"((?:Dr\.?\s+)?[A-ZÀ-Þ][a-zß-ÿ'\-]+(?:\s+[A-ZÀ-Þ][a-zß-ÿ'\-]+){1,2})"
OWNER_PATTERNS = [
    re.compile(ROLE + r"\s*[:\-–|,]?\s*" + NAME),                       # Founder: Jane Smith
    re.compile(NAME + r"\s*[,\-–|(]?\s*(?:(?i:our|the)\s+)?" + ROLE),   # Jane Smith, Owner
    re.compile(r"(?i:founded)(?:\s+in\s+\d{4})?\s+(?i:by)\s+" + NAME),  # founded by Jane Smith
]
FOUNDER_DATA = re.compile(r'"founder"\s*:\s*(?:\[\s*)?(?:\{[^{}]*?"name"\s*:\s*)?"([^"]{3,60})"')
# Words that look like names in headings ("Meet Our Team") but are not people
NOT_NAME_WORDS = {"Our", "The", "Meet", "Team", "About", "Contact", "Home", "Welcome", "Read",
                  "More", "Message", "Since", "Company", "Board", "And", "With", "From", "Your",
                  "View", "Profile", "Office", "Group", "Services", "Clinic", "Ltd", "Llc",
                  "Inc", "Gmbh", "Founder", "Owner", "Director", "Managing", "Chief", "Today",
                  "Us", "Call", "Email", "Book", "Now", "Here"}
HIDDEN_REGISTRANT = ("redact", "privacy", "private", "proxy", "withheld", "protect", "gdpr",
                     "not disclosed", "data", "masked", "registrant", "whois", "domain")
TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)


# --- finding things in a page -------------------------------------------------
def _cf_decode(hex_text: str) -> str:
    """Cloudflare hides emails as XOR-ed hex; the first byte is the key."""
    data = bytes.fromhex(hex_text)
    return "".join(chr(b ^ data[0]) for b in data[1:])


def find_emails(page: str) -> list[str]:
    text = unquote(html.unescape(page)).replace("(at)", "@").replace("[at]", "@")
    found = [m.group(0) for m in EMAIL.finditer(text)]
    found += [_cf_decode(m.group(1)) for m in CFEMAIL.finditer(page)]
    clean = []
    for email in found:
        # "info@acme.comClifton": page text glued onto the address; cut where the case flips
        name, _, host = email.strip(".").rpartition(".")
        ending = re.match(r"[a-z]+|[A-Z]+", host)
        email = f"{name}.{ending.group(0) if ending else host}".lower()
        domain = email.split("@", 1)[1]
        names = domain.split(".")
        if email.endswith(NOT_EMAIL_ENDINGS) or domain in PLACEHOLDER_DOMAINS or                 any(n in PLACEHOLDER_NAMES for n in names):
            continue
        if len(email) <= 80 and email not in clean:
            clean.append(email)
    return clean


def find_socials(page: str) -> dict[str, str]:
    found = {}
    for network, pattern in SOCIAL.items():
        match = pattern.search(page)
        if match:
            link = match.group(0).rstrip("/.\\")
            found[network] = "https:" + link if link.startswith("//") else link
    return found


def _person(name: str) -> str | None:
    name = " ".join(name.split())
    words = [w for w in name.split() if w not in ("Dr", "Dr.")]
    if not 2 <= len(words) <= 3 or any(w in NOT_NAME_WORDS for w in words):
        return None
    return name


def find_owner(page: str) -> str | None:
    """The owner's or founder's name on a page, if it says so plainly."""
    for match in FOUNDER_DATA.finditer(page):
        if person := _person(html.unescape(match.group(1))):
            return person
    text = " ".join(html.unescape(TAGS.sub(" ", page)).split())
    # "Jane Smith Co-Founder": "Co" must not be read as part of the name
    text = re.sub(r"\bco[\s-]+(?=founder)", "co", text, flags=re.I)
    for pattern in OWNER_PATTERNS:
        for match in pattern.finditer(text):
            if person := _person(match.group(1)):
                return person
    return None


def registrant(rdap: dict) -> str | None:
    """The registrant's name in a domain record, unless it is hidden for privacy."""
    for entity in rdap.get("entities", []):
        if "registrant" not in entity.get("roles", []):
            continue
        for item in (entity.get("vcardArray") or [None, []])[1]:
            if len(item) == 4 and item[0] in ("fn", "org") and isinstance(item[3], str):
                name = item[3].strip()
                if len(name) > 2 and not any(w in name.lower() for w in HIDDEN_REGISTRANT):
                    return name
    return None


def find_profiles(page: str) -> list[str]:
    """The LinkedIn profiles of people a page links to, in page order."""
    links = (match.group(0).rstrip("/.\\") for match in PROFILE.finditer(page))
    return list(dict.fromkeys("https:" + link if link.startswith("//") else link
                              for link in links))


def owner_profile(profiles: list[str], owner: str | None) -> str:
    """The owner's profile among those the website links: the one whose address has the
    owner's surname, or the only one there is. LinkedIn blocks automatic reading and free
    search engines block automatic searching (tested 2026-10-17), so the website is the
    only source; anything else is NOT_FOUND."""
    if owner:
        surname = owner.split()[-1].lower()
        named = [link for link in profiles if surname in unquote(link).lower()]
        if named:
            return named[0]
    return profiles[0] if len(profiles) == 1 else NOT_FOUND


def social_network(url: str) -> str | None:
    """The network a URL belongs to, if a business gave a social page as its website."""
    for network, pattern in SOCIAL.items():
        if pattern.match(url or ""):
            return network
    return None


def contact_links(page: str, base: str) -> list[str]:
    host = urlsplit(base).netloc
    links = []
    for href in HREF.findall(page):
        url = urljoin(base, href.strip())
        if urlsplit(url).netloc == host and any(w in url.lower() for w in CONTACT_WORDS) \
                and url not in links and url.rstrip("/") != base.rstrip("/"):
            links.append(url)
    return links[: MAX_PAGES - 1]


# --- company age ---------------------------------------------------------------
def domain_candidates(domain: str) -> list[str]:
    """'shop.acme.co.uk' -> ['shop.acme.co.uk', 'acme.co.uk', 'co.uk']: tried in order.

    Nothing for a site on a website builder, whose domain says nothing about the business.
    """
    domain = domain.lower().strip(".").removeprefix("www.")
    if any(domain == s or domain.endswith("." + s) for s in HOSTED_SUFFIXES):
        return []
    labels = domain.split(".")
    return [".".join(labels[i:]) for i in range(len(labels) - 1)]


def registration_date(rdap: dict) -> date | None:
    for event in rdap.get("events", []):
        if event.get("eventAction") == "registration" and event.get("eventDate"):
            return datetime.fromisoformat(event["eventDate"][:10]).date()
    return None


def age_fields(created: date | None, source: str = "Domain registration",
               today: date | None = None) -> dict:
    if created is None:
        return {}
    years = ((today or date.today()) - created).days // 365
    span = "under 1 year" if years < 1 else f"{years} year" + ("" if years == 1 else "s")
    label = f"Startup ({span})" if years < STARTUP_YEARS else f"Established ({span})"
    return {"domain_created": created.isoformat(), "company_age": label, "age_years": years,
            "age_source": source}


# --- network ---------------------------------------------------------------------
class Enricher:
    """Shared by many threads; one connection pool, one domain-age cache."""

    def __init__(self, transport: httpx.BaseTransport | None = None, wayback: bool = True):
        # wayback: fall back to the (slow) archive lookup when the registry gives no date.
        # Only worth it when the user is filtering by age.
        self.wayback = wayback
        # verify=False: small-business sites often have broken certificates, and we only
        # read public pages and send nothing, so a failed check would just lose the lead's email
        self.http = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=10,
                                 follow_redirects=True, verify=False, transport=transport)
        self._ages: dict[str, tuple[date | None, str]] = {}
        self._registrants: dict[str, str | None] = {}
        self._wayback = threading.Semaphore(WAYBACK_AT_ONCE)

    def close(self) -> None:
        self.http.close()

    def _get(self, url: str) -> str:
        with self.http.stream("GET", url) as response:
            if response.status_code >= 400 or "html" not in response.headers.get(
                    "content-type", "html"):
                return ""
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size >= MAX_BYTES:
                    break
            return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")

    def crawl(self, url: str, keep_text: bool = False) -> dict:
        emails: list[str] = []
        socials: dict[str, str] = {}
        profiles: list[str] = []
        owner, text = None, ""
        queue, seen = [url], set()
        while queue and len(seen) < MAX_PAGES:
            page_url = queue.pop(0)
            seen.add(page_url)
            try:
                page = self._get(page_url)
            except (httpx.HTTPError, ValueError):
                continue
            emails += [e for e in find_emails(page) if e not in emails]
            for network, link in find_socials(page).items():
                socials.setdefault(network, link)
            profiles += [link for link in find_profiles(page) if link not in profiles]
            owner = owner or find_owner(page)
            if page_url == url:
                queue += contact_links(page, url)
            if page_url == url and keep_text:
                text = " ".join(html.unescape(TAGS.sub(" ", page)).split())[:SITE_TEXT]
        return {"emails": emails, "socials": socials, "profiles": profiles, "owner": owner,
                "text": text}

    def domain_created(self, domain: str) -> tuple[date | None, str]:
        """When the domain was registered, else first archived; and which of the two."""
        if domain in self._ages:
            return self._ages[domain]
        candidates = domain_candidates(domain)
        created = None
        for candidate in candidates:
            try:
                response = self.http.get(f"https://rdap.org/domain/{candidate}")
            except httpx.HTTPError:
                break
            if response.status_code == 200:
                try:
                    record = response.json()
                    created = registration_date(record)
                    self._registrants[domain] = registrant(record)
                except ValueError:
                    pass
                break
        result = (created, "Domain registration")
        if created is None and candidates and self.wayback:
            result = (self.first_archived(candidates[0]), "First seen online (Wayback Machine)")
        self._ages[domain] = result
        return result

    def first_archived(self, domain: str) -> date | None:
        with self._wayback:
            try:
                response = self.http.get(
                    "https://web.archive.org/cdx/search/cdx",
                    params={"url": domain, "limit": "1", "fl": "timestamp", "output": "json"},
                    timeout=15)
                rows = response.json() if response.status_code == 200 else []
            except (httpx.HTTPError, ValueError):
                return None
        if len(rows) > 1 and rows[1]:
            return datetime.strptime(rows[1][0][:8], "%Y%m%d").date()
        return None

    def enrich(self, lead: dict, find_contacts: bool = True, find_owner: bool = False,
               site_text: bool = False) -> dict:
        """The new fields for one lead (does not modify it). ``site_text``: keep the start of
        the home page's text, for Smart mode to read."""
        fields: dict = {"enriched": True}
        website = lead.get("website") or ""
        if PROFILE.match(website):  # a freelancer's own profile given as the website
            return {**fields, "owner_linkedin": website} if find_owner else fields
        network = social_network(website)
        if network:
            # A Facebook or Instagram page given as the website: file it under that
            # network and do not crawl it (social sites block plain requests)
            fields[network] = website
            return fields
        if not website:
            return fields
        found = {"owner": None, "profiles": [], "text": ""}
        if find_contacts or site_text:
            found = self.crawl(website, keep_text=site_text)
        if site_text and found["text"]:
            fields["site_text"] = found["text"]
        if find_contacts:
            domain = (lead.get("domain") or urlsplit(website).netloc).lower()
            own = [e for e in found["emails"] if e.endswith("@" + domain.removeprefix("www."))]
            emails = own + [e for e in found["emails"] if e not in own]
            if emails:
                fields["emails"] = ", ".join(emails[:MAX_EMAILS])
            fields.update({"linkedin": NOT_FOUND, **found["socials"]})
        domain = lead.get("domain") or urlsplit(website).netloc
        if domain:
            fields.update(age_fields(*self.domain_created(domain)) or {"company_age": "Unknown"})
        if find_owner:
            if found["owner"]:
                fields.update(owner_name=found["owner"], owner_source="Website")
            elif self._registrants.get(domain):
                fields.update(owner_name=self._registrants[domain], owner_source="Domain record")
            fields["owner_linkedin"] = owner_profile(found["profiles"], fields.get("owner_name"))
        return fields
