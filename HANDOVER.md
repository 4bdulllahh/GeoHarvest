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
| Country search | Works worldwide (live-tested 2026-10-16: US, UAE, Germany, France, UK, Spain, Netherlands, Italy, Pakistan, GCC). The Countries box takes several countries and the regions **European Union** (27) and **Gulf (GCC)** (`geo.REGIONS`), plus typed shorthand like USA/UK/UAE (`geo.ALIASES`). On the Search page countries and cities are **tick-box checklists** (`widgets/checklist.py`): ticking a country lists its cities and pre-ticks the biggest `city_count`; a region ticks all its members; places not listed can be added. Options store ticked cities as "City, Country"; with no cities (old saves) each country's biggest `city_count` are used. Options key is `countries` (list); old `country` strings are converted in `options_with_defaults`. EU/UK connections get Google's consent page: `MapsClient` sends `CONSENT`/`SOCS` cookies (untested from an EU IP: dev machine is in the UAE) |
| App name | **GeoHarvest** (renamed from MapScout on 2026-10-16 to match the repo github.com/4bdulllahh/GeoHarvest; the local folder is still called MapScout). Data folder: `%APPDATA%/GeoHarvest` |
| Startup vs established | Google Maps has no founding date. Estimated from the domain's registration date (RDAP via rdap.org, free). Registries without RDAP dates (.pk and others) fall back to the first Wayback Machine snapshot, but **only when the user picks Startups or Established**, because it is slow (5-15 s per site; added ~40 s to a 60-lead search). Sites on website builders (netlify.app, wixsite.com...) get no age. Column "Age based on" says which source was used. Startup = under 3 years |
| AI providers | All of them, user brings their own key: Gemini (plain HTTPS, JSON mode), Claude (official `anthropic` SDK: structured JSON output, effort `low`, server-side refusal fallbacks on Opus 5.5 / Opus 5 / Sonnet 5.5 / Fable 5.1; default model `claude-opus-5-5`, note suggests Haiku 5.5 as cheapest), and one OpenAI-compatible connector (plain HTTPS) with presets for Groq, OpenRouter, Mistral, OpenAI, DeepSeek, Ollama and LM Studio (local), plus a custom URL. Default model names for non-Claude providers may go stale: the "Load models" button lists the real ones. Keys are DPAPI-encrypted in `%APPDATA%/GeoHarvest/secrets.dat` (`app/core/credentials.py`, from HomingPigeon) |
| Extras | Emails and social links from each business website; filters (min rating, min reviews, has website/phone, hide closed); history with resume; auto-updater from GitHub releases |
| Cost | Nothing paid. No paid APIs, no proxies |
| Release | GitHub Releases, `GeoHarvest-vX.Y.Z-windows.zip` holding `GeoHarvest-Setup.exe`, its `runtime/` folder and `READ ME FIRST.txt` (since 0.1.2; must be extracted first). **Own installer** `installer/setup_app.py`: Tkinter, standard library only, copied from HomingPigeon's (`Email-Sender/installer/setup_app.py`) for the look (welcome card, step list with ticks, progress bar, activity log, finish page with Start menu / Desktop / open-at-Windows-start (unticked) / open-now). PyInstaller one-folder with `--contents-directory runtime`, never one-file (HomingPigeon's one-file Setup was flagged by Defender as Wacatac). Carries the app folder as `payload.zip` (LZMA). Installs per user to `%LOCALAPPDATA%\Programs\GeoHarvest` (no admin), writes `version.txt`, keeps a copy of itself minus the payload in `<app>\uninstall\` as the uninstaller, registers HKCU `...\Uninstall\GeoHarvest`. The app's Update now runs `GeoHarvest-Setup.exe --update --target <app folder>` directly (no batch file, no console; `PYINSTALLER_RESET_ENVIRONMENT=1`); Setup waits for the app to close, updates, reopens it. Settings > Uninstall asks keep/delete data in the app, then runs `uninstall\GeoHarvest-Setup.exe --uninstall --confirmed [--delete-data]`. Setup also accepts 0.1.1's Inno-style `/SILENT /DIR=` and removes 0.1.1's Inno registry entry and `unins000.*`. Version check compares numbers only (tags are written with and without "beta"). No accounts, everything local |
| Stop after N | Means N leads **kept** after the age filter and Smart mode's minimum score. Removals give the count back; query threads wait (`room()` in `workers/scrape.py`) while saved leads are still being checked, then continue if any were dropped. "Leave out businesses I found in earlier searches" is on by default since 0.1.1 |
| Languages | English only for v0.1. `app/i18n.py` is a pass-through `t()` so HomingPigeon's translation system can drop in later |

## Milestones

- [x] **1. Shell**: window, sidebar, theme, logo, settings storage (`app/core/db.py`), placeholder pages, Settings appearance controls, this file, README outline
- [x] **2. Scraper engine**: `app/core/scraper.py` (HTTP client + paging), `app/core/places.py` (Google's arrays -> lead dict, `FIELDS` = column order), `app/core/search.py` (options, queries, filters, saving, resume progress), `app/core/geo.py` + `app/data/cities.json` (244 countries, top 60 cities, built by `tools/build_cities.py`), `app/workers/scrape.py` (`ScrapeWorker`: parallel queries, saves every page, `stop()`, Blocked handling), `tests/test_core.py`
- [x] **3. Search and Leads pages**: `pages/search.py` (form remembers last options in setting `last_options`, comma-list autocomplete for niches and cities, live stat tiles, Stop, Open leads; `run(search_id)` also resumes), `pages/leads.py` (search picker, instant filter, sort, hides empty columns, live rows via `MainWindow.leads_added`, right-click copy/open, delete search), `widgets/leads_model.py`, `core/exporter.py` (xlsx + csv, only used columns, formula-injection safe)
- [x] **4. Enrichment**: `app/core/enrich.py` (`Enricher`: home page + up to 3 contact/about pages, 2 MB cap per page, emails incl. Cloudflare-obfuscated and HTML-entity ones, own-domain emails first, socials; social pages given as "website" are filed under that network and not crawled; RDAP + Wayback age). Runs inside `ScrapeWorker` in a 16-thread pool alongside the search; the age filter deletes non-matching leads (`removed` signal -> Leads table). Lead key `enriched` marks done, so resume re-checks only the rest
- [x] **5. Smart mode**: `app/core/ai.py` (providers, prompt, batch of 8 leads per request, tolerant JSON parsing, 429 wait-and-retry, fatal vs skippable errors, `test()` scores a sample lead), `app/workers/ai.py` (`AIStage`: scoring thread fed while the search runs, after enrichment; `AIScoreWorker`: Leads page "Score with AI"), `pages/smart.py` (provider buttons, key, address for local/custom, model + Load models, ideal customer text, "leave out below N", Save and test, Turn off). Verdict comes from the score in code: 80+ Good fit, 50-79 Maybe, else Poor fit. A fatal AI error leaves the search `stopped` so resume re-scores
- [x] **6. History, resume, updater, Settings**: `pages/history.py` (open leads, resume, run again, delete), `search.recover_interrupted()` at start-up, `SearchPage.load_options()`, `app/services/updater.py` + `widgets/update_dialog.py` (GitHub latest release, asset `GeoHarvest-vX.Y.Z-windows.zip`, SHA-256 check, `install.bat` waits for the app to exit, robocopy **/E never /MIR**, restarts; only when frozen), Settings (speed Gentle 2 / Normal 4 / Fast 8 parallel searches, updates, data folder, delete all, fair-use note), styled spin box arrows
- [x] **7. Release**: `tools/build.py` (PyInstaller one-folder, unused Qt/numpy/PIL/lxml/cryptography left out: 38 MB zip, then runs `GeoHarvest.exe --self-test`), `.github/workflows/build.yml` (tests + build on every push; on a published release it attaches the zip), `tools/screenshot.py` (README screenshots from fictional demo data in a throwaway data folder), full README, release notes in `docs/releases/v0.1.0-beta.md`. The GitHub release itself is published by the user

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
app/core/ai.py             Smart mode providers, prompt, scoring
app/core/credentials.py    DPAPI-encrypted secret store (AI keys)
app/workers/ai.py          AIStage (during a search), AIScoreWorker (on demand)
app/ui/widgets/leads_model.py  LeadsModel (append/update rows live) + LeadsProxy (filter/sort)
app/workers/base.py        Task / Worker on a QThreadPool (from HomingPigeon)
app/ui/theme.py            colour tokens + the one stylesheet (from HomingPigeon)
app/ui/main_window.py      sidebar, lazy-built pages, status bar
app/ui/pages/              one module per page
app/ui/widgets/            shared widgets (from HomingPigeon)
assets/                    logo.svg, PNG sizes, icon.ico
tools/make_icons.py        logo.svg -> PNGs + ico
tools/screenshot.py        README screenshots from made-up demo data
tools/build.py             build app + installer + zip + self-test the Windows release
installer/setup_app.py     GeoHarvest Setup: install, update, uninstall (Tkinter, HomingPigeon's look)
installer/READ ME FIRST.txt  goes in the release zip
.github/workflows/build.yml  CI build; attaches the zip to published releases
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
python tools/screenshot.py    # refresh README screenshots (demo data)
python tools/build.py         # dist/GeoHarvest-vX.Y.Z-windows.zip (installer inside) + self-test
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
- 2026-10-16: Milestone 5 done. Not tested against a real AI provider (no key or local model on
  the dev machine). Tested end to end against a fake OpenAI-compatible server: Save and test, a real
  40-lead Google search with Smart mode, batches of 8, low scores removed, tiles and status correct.
  First thing to check with a real key: Gemini and Claude replies parse (unit tests cover the
  OpenAI-style path and errors only).
- 2026-10-16: Milestone 6 done. Multi-country support added at the user's request (they target
  UAE, USA and the EU, not just Pakistan). Stop + resume tested live: 297 saved at stop, resume
  finished with 1,033 unique leads, no duplicates. City falls back to Google's locality field [166]
  (UAE addresses have no city part). Junk emails now filtered in NL/DE/FR/ES/IT too. The self-update
  install step can only be tested on a packaged build (milestone 7).
- 2026-10-16: Milestone 7 done. Countries and cities became tick-box checklists at the user's
  request. Packaged exe verified: GUI starts, `--self-test` passes (imports, live search, Excel
  export), and the updater's install.bat tested against the real build (copied new files, kept a
  user file in the app folder, restarted the app).
- 2026-10-16: v0.1.1 beta: Inno Setup installer in the release zip, Settings > Uninstall,
  "Stop after N" counts kept leads only, skip-known on by default, Stop no longer waits for
  website checks or AI requests in flight (closes the connection and drops their results;
  resume re-checks them). Tested: installer silent install, self-test of the installed exe,
  reinstall over it, uninstall (data kept). 0.1.0 copies cannot self-update to 0.1.1 (their
  updater looks for GeoHarvest.exe in the zip): those users install 0.1.1 by hand once.
- 2026-10-16: v0.1.2 beta: Inno Setup replaced by our own installer in HomingPigeon's style, at the
  user's request. Fixes: the app offered "v0.1.1" to "v0.1.1 beta" forever (the release was tagged
  without "beta"); Update now opened a visible cmd window (DETACHED_PROCESS made Windows ignore
  CREATE_NO_WINDOW, so tasklist/find got their own console). Tested: Setup's update mode into a
  test folder (installs, opens the app), the installed uninstaller (removes everything, keeps
  data), screenshots of welcome/progress/remove pages. Not tested: a real default-folder install
  over the user's 0.1.1, and 0.1.1's updater driving the new Setup (/SILENT path).

## Releasing a new version

1. Bump `APP_VERSION` in `app/config.py` (e.g. "v0.2.0 beta"); write `docs/releases/<tag>.md`.
2. Commit and push; check the Actions run is green.
3. On GitHub: Releases > Draft a new release, tag `v0.2.0-beta` (the version with a hyphen),
   paste the notes, Publish. The workflow attaches `GeoHarvest-v0.2.0-beta-windows.zip` within
   about 5 minutes; every installed copy then offers the update on its next start.

## Working agreement

After every milestone: update this file, commit, push, then ask the user before starting the next one.
