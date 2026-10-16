# GeoHarvest handover

Read this first when picking the work back up (person or Claude). It says what
is done, what is next, and the decisions already made so nobody re-asks them.

## The product

A free Windows desktop app (Python + PyQt6) that finds business leads on Google
Maps, like omkarcloud's google-maps-scraper but faster and easier to use. The
user types a niche (restaurant, real estate...), picks a country (and optionally
cities) and a company age (startup / established / any), and gets every
business with maximum detail, exported to Excel. Two modes:

- **Quick mode**: scrape only.
- **Smart mode**: the user adds their own AI key (or a local model) and the AI
  scores each lead against the user's description of an ideal customer.

The UI copies HomingPigeon (https://github.com/4bdulllahh/HomingPigeon): same
theme module, sidebar, cards, status bar, worker pattern.

## Decisions already made (do not re-ask)

| Topic | Decision |
|---|---|
| UI toolkit | PyQt6, Fusion style, one app-wide stylesheet from `app/ui/theme.py` (copied from HomingPigeon) |
| Logo | A pitchfork driven *through* a folded map (user's choice, not a map pin). `assets/logo.svg`, rendered by `tools/make_icons.py` |
| Scraping | **Plain HTTPS, no browser.** We call the same `/search?tbm=map&pb=...` endpoint the Google Maps page uses, with the full `pb` template captured from a real Edge session (`app/data/maps_pb.txt`). 20 places per request, ~1 s each, pages via `!8i<offset>`. Measured 2026-10-16: 6 cities in parallel, 1,255 unique businesses in 36 s, no blocking. A hand-written short `pb` returns an empty shell, so keep the captured template. If Google changes the format: run `scratchpad`-style capture again (Playwright + Edge, record responses containing `tbm=map`) and refresh the template and `tests/fixtures/maps_page.json` |
| Results per search | Google stops paging at about 200 per query; wide coverage comes from sweeping cities |
| Country search | Google caps one search at roughly 120 results, so "country only" sweeps that country's biggest cities one by one; the user can also type cities |
| App name | **GeoHarvest** (renamed from MapScout on 2026-10-16 to match the repo github.com/4bdulllahh/GeoHarvest; the local folder is still called MapScout). Data folder: `%APPDATA%/GeoHarvest` |
| Startup vs established | Google Maps has no founding date. Estimated from the domain's registration date (RDAP via rdap.org, free). Registries without RDAP dates (.pk and others) fall back to the first Wayback Machine snapshot, but **only when the user picks Startups or Established**, because it is slow (5-15 s per site; added ~40 s to a 60-lead search). Sites on website builders (netlify.app, wixsite.com...) get no age. Column "Age based on" says which source was used. Startup = under 3 years |
| AI providers | All of them, user brings their own key: Google Gemini, Anthropic Claude, and one OpenAI-compatible connector with presets for OpenAI, Groq, OpenRouter, Mistral, DeepSeek, Ollama (local) and LM Studio (local), plus a custom URL. Plain httpx, no SDKs |
| Extras | Emails and social links from each business website; filters (min rating, min reviews, has website/phone, hide closed); history with resume; auto-updater from GitHub releases |
| Cost | Nothing paid. No paid APIs, no proxies |
| Release | GitHub Releases, `GeoHarvest-vX.Y.Z-windows.zip` with `GeoHarvest.exe` inside (PyInstaller one-folder: fast start, fewer antivirus false alarms). First release v0.1.0 beta after all milestones |
| Languages | English only for v0.1. `app/i18n.py` is a pass-through `t()` so HomingPigeon's translation system can drop in later |

## Milestones

- [x] **1. Shell**: window, sidebar, theme, logo, settings storage (`app/core/db.py`), placeholder pages, Settings appearance controls, this file, README outline
- [x] **2. Scraper engine**: `app/core/scraper.py` (HTTP client + paging), `app/core/places.py` (Google's arrays -> lead dict, `FIELDS` = column order), `app/core/search.py` (options, queries, filters, saving, resume progress), `app/core/geo.py` + `app/data/cities.json` (244 countries, top 60 cities, built by `tools/build_cities.py`), `app/workers/scrape.py` (`ScrapeWorker`: parallel queries, saves every page, `stop()`, Blocked handling), `tests/test_core.py`
- [x] **3. Search and Leads pages**: `pages/search.py` (form remembers last options in setting `last_options`, comma-list autocomplete for niches and cities, live stat tiles, Stop, Open leads; `run(search_id)` also resumes), `pages/leads.py` (search picker, instant filter, sort, hides empty columns, live rows via `MainWindow.leads_added`, right-click copy/open, delete search), `widgets/leads_model.py`, `core/exporter.py` (xlsx + csv, only used columns, formula-injection safe)
- [x] **4. Enrichment**: `app/core/enrich.py` (`Enricher`: home page + up to 3 contact/about pages, 2 MB cap per page, emails incl. Cloudflare-obfuscated and HTML-entity ones, own-domain emails first, socials; social pages given as "website" are filed under that network and not crawled; RDAP + Wayback age). Runs inside `ScrapeWorker` in a 16-thread pool alongside the search; the age filter deletes non-matching leads (`removed` signal -> Leads table). Lead key `enriched` marks done, so resume re-checks only the rest
- [ ] **5. Smart mode**: provider settings and key test, "ideal customer" text, per-lead score 0-100 with a verdict and a one-line reason, filter by score
- [ ] **6. History, resume, updater, Settings**: Past searches page, resume a stopped search, auto-update from GitHub releases, speed settings
- [ ] **7. Release**: PyInstaller build script, GitHub Actions workflow, full README with screenshots, tag v0.1.0-beta

## Layout

```
run.py                     launcher (crash guard, theme, window)
app/config.py              paths (%APPDATA%/GeoHarvest), version, repo URL
app/i18n.py                t(): pass-through for now
app/core/                  no UI imports; business logic, unit tested
  db.py                    SQLite: settings, searches, leads (lead = one JSON doc)
  prefs.py                 Settings defaults
  scraper.py               Google Maps over HTTPS: MapsClient.fetch, search() pager, Blocked
  places.py                parse one raw place; FIELDS (key, header) = table/export columns
  search.py                options dict, build_queries, passes (filters), save/update leads
  geo.py                   countries and cities from app/data/cities.json
app/data/                  cities.json (GeoNames CC BY 4.0), maps_pb.txt (Google request template)
app/workers/scrape.py      ScrapeWorker: runs a search's queries in parallel, resumable
app/core/exporter.py       Excel/CSV export
app/core/enrich.py         website emails/socials, company age (RDAP, Wayback)
app/ui/widgets/leads_model.py  LeadsModel (append/update rows live) + LeadsProxy (filter/sort)
app/workers/base.py        Task / Worker on a QThreadPool (from HomingPigeon)
app/ui/theme.py            colour tokens + the one stylesheet (from HomingPigeon)
app/ui/main_window.py      sidebar, lazy-built pages, status bar
app/ui/pages/              one module per page
app/ui/widgets/            shared widgets (from HomingPigeon)
assets/                    logo.svg, PNG sizes, icon.ico
tools/make_icons.py        logo.svg -> PNGs + ico
tools/screenshot.py        opens the app and saves each page to docs/screenshots/
```

## Rules carried over from HomingPigeon

- Nothing slow on the UI thread: browser, network, export all go through `app/workers/`.
- `app/core/` never imports PyQt.
- Plain English on screen; no developer jargon.
- Never `git push` unless the user asks.

## Commands

```
pip install -r requirements-dev.txt
python run.py                 # run the app
python -m pytest tests/ -q    # tests
python tools/screenshot.py    # refresh README screenshots
python tools/make_icons.py    # after editing assets/logo.svg
```

## Log

- 2026-10-16: Milestone 1 done.
- 2026-10-16: Milestone 2 done. Switched from Playwright to plain HTTPS after testing (faster, no
  browser needed). Live test: 660 real estate agencies in 3 Pakistani cities in 41 s.
  Google's field [57] is the business's own account, not a person: shown only as "Claimed by owner".
  Description ([32]) is mostly filled for restaurants/hotels only. Price is rarely present.
- 2026-10-16: Milestone 3 done. UI smoke test: real search (dentists, Lahore, stop after 80)
  streamed into the Search tiles and the Leads table. Known cosmetic issue: QSpinBox arrows are
  unstyled dark squares (add QSS for ::up-button/::down-button). Some businesses list a
  Facebook/Instagram page as their "website"; milestone 4 should move those into the social columns.
- 2026-10-16: Milestone 4 done. Renamed the app to GeoHarvest. Live: 60 Lahore dentists with all
  websites checked in 20 s (22 emails, 22 Facebook, 25 Instagram). "Stop after N" counts leads before
  the age filter removes any (hint says so). Not done: emails from Facebook pages (social sites block
  plain requests).

## Working agreement

After every milestone: update this file, commit, push, then ask the user before starting the next one.
