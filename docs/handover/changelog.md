# Changelog

What went into each version and how it was tested, newest first. Add to it with every change. The user-facing release notes are in `docs/releases/`.

## v0.3.0 beta (2026-10-29)

**v0.3.0 (started 2026-10-29).** The user tested v0.2.2 and asked for a big batch.
Agreed plan (form answers), in order, pausing to ask after milestones 2, 3 and 8:
1. [x] Requirements: "Which businesses?" renamed Requirements, every choice a select button,
   min/max sliders (rating, reviews, company age in years with Any/Startups/Established/My own
   range quick buttons), Name can be unpicked (none picked = Name), new must-haves (email,
   social media, LinkedIn, owner, claimed, hours listed), Quick setup (Cold email / Cold calling /
   Build a database, `search.USE_CASES`)
2. [x] Finding pipeline: "Stop after" -> **Minimum leads**, every match kept best first, digs
   deeper by itself, asks before adding cities or related types; score = info found + a little
   reputation, low scores ranked last, breakdown in the lead window (see "Finding (0.3)" below)
3. [x] Updates: no switch; check + download latest on open, install right away unless a search
   runs; Setup (0.3+) fetches the newest release instead of installing an old one, offline it
   installs what it has; Settings > Updates = version + Check now + GitHub page
4. [x] HomingPigeon look: themes + theme maker + share file, smooth scrolling, menu order/hide,
   reset appearance
5. [x] Resizing: rows wrap, side-by-side parts stack, sidebar shrinks to icons below ~1000 px,
   remember window size and place
6. [x] Leads page: Sort menu, Show menu, date range, rating/reviews sliders, copy emails/phones,
   export only new leads, export for HomingPigeon, score breakdown (done in 2)
7. [x] Settings/extras: backup + restore + weekly auto backup (keep 4), first page on open,
   date/time format, forget saved keys, report a problem, Start here guide page, notify when a
   search finishes, requirement presets, live estimate on the form
8. [x] Languages: Arabic (RTL), German, Spanish, French via HomingPigeon's i18n package; Claude
   wrote the translations (see "Languages (0.3)" below)
9. [x] Build v0.3.0 zip, release notes, README (the install-if-blocked .bat moved to v0.3.1)

## v0.2.2 beta (2026-10-17)

**State of v0.2.2 when the session ended (2026-10-17):**
- Code, `docs/releases/v0.2.2-beta.md` and README pushed; the GitHub Actions run was green.
- Built locally too: `dist/GeoHarvest-v0.2.2-beta-windows.zip` (32 MB, packaged self-test OK
  with a real 20-lead search). `dist/` is not in git: it only changes when someone runs
  `python tools/build.py`. Publishing the GitHub release makes the workflow attach its own
  copy of the zip.
- The user was going to publish release `v0.2.2` and **test it themselves**, then come back
  with fixes and changes. Start by asking what they found (form), then follow the steps below.

**What went into v0.2.2** (the user's requests and their form answers):
- [x] **A. Search pipeline**: three steps one after another, candidates, quality score,
  balanced pick, shortfall explanation with "Add 10 more cities" / "Allow any company age",
  hidden addresses (see the "Three-step search" and "Hidden addresses" rows below)
- [x] **B. New search UI**: business-type picker at the top of New search (typing filters a
  grouped list in columns; several can be picked; own types still allowed). "Details to include"
  and Leads > Columns are select/unselect buttons (selected = highlighted like Settings'
  Theme buttons, unselected = greyed) instead of switches. Switches stay everywhere else
  (country/city lists, must-have filters, hours)
- [x] **C. LinkedIn**: people-search links dropped; company page and owner's profile come from
  the business's website, else "N/A" (see the "Owner's name" row; a free web search was tested
  and every engine blocked it)
- Unknown company ages (many .ae sites: the registry hides dates and Wayback often has
  nothing) are **kept** for Startups/Established (user's choice), marked "Unknown" and ranked
  after known ages (`pick()` key in `workers/scrape.py`)
- Licence: user keeps PyQt6 for now (no plan to sell closed source); PySide6 is the route if that
  changes (mostly renaming imports, `pyqtSignal` -> `Signal`)

**What the user should test in v0.2.2** (nobody has done these yet):
1. Install the zip over v0.2.1 (and Update now from v0.2.1 once the release is published).
2. A multi-city, multi-type search with "Stop after" (e.g. 400): the three steps, the tiles
   only counting up, the leads spread over the cities, and the summary if it comes up short.
3. **Add 10 more cities** and **Allow any company age** after a short search.
4. The business-type picker with a real mouse and keyboard (click, type to narrow, Enter for
   an own type, Esc).
5. Details to include and Leads > Columns: selected/greyed look in dark and light themes.
6. Smart mode with a real AI key in the new flow (the AI now runs in step 3).
7. Resume and Stop on a big search; resuming a search made before v0.2.2.

## The first seven milestones (v0.1.0)

- [x] **1. Shell**: window, sidebar, theme, logo, settings storage (`app/core/db.py`), placeholder pages, Settings appearance controls, this file, README outline
- [x] **2. Scraper engine**: `app/core/scraper.py` (HTTP client + paging), `app/core/places.py` (Google's arrays -> lead dict, `FIELDS` = column order), `app/core/search.py` (options, queries, filters, saving, resume progress), `app/core/geo.py` + `app/data/cities.json` (244 countries, top 60 cities, built by `tools/build_cities.py`), `app/workers/scrape.py` (`ScrapeWorker`: parallel queries, saves every page, `stop()`, Blocked handling), `tests/test_core.py`
- [x] **3. Search and Leads pages**: `pages/search.py` (form remembers last options in setting `last_options`, comma-list autocomplete for niches and cities, live stat tiles, Stop, Open leads; `run(search_id)` also resumes), `pages/leads.py` (search picker, instant filter, sort, hides empty columns, reloads when a search picks its leads, right-click copy/open, delete search), `widgets/leads_model.py`, `core/exporter.py` (xlsx + csv, only used columns, formula-injection safe)
- [x] **4. Enrichment**: `app/core/enrich.py` (`Enricher`: home page + up to 3 contact/about pages, 2 MB cap per page, emails incl. Cloudflare-obfuscated and HTML-entity ones, own-domain emails first, socials; social pages given as "website" are filed under that network and not crawled; RDAP + Wayback age). Runs as step 2 of `ScrapeWorker` in a 16-thread pool (since 2026-10-17; it used to run alongside the search). Lead key `enriched` marks done, so resume re-checks only the rest
- [x] **5. Smart mode**: `app/core/ai.py` (providers, prompt, batch of 8 leads per request, tolerant JSON parsing, 429 wait-and-retry, fatal vs skippable errors, `test()` scores a sample lead), `app/workers/ai.py` (`AIScoreWorker`: Leads page "Score with AI"; during a search the AI runs in step 3 of `ScrapeWorker`), `pages/smart.py` (provider buttons, key, address for local/custom, model + Load models, ideal customer text, "leave out below N", Save and test, Turn off). Verdict comes from the score in code: 80+ Good fit, 50-79 Maybe, else Poor fit. A fatal AI error leaves the search `stopped` so resume re-scores
- [x] **6. History, resume, updater, Settings**: `pages/history.py` (open leads, resume, run again, delete), `search.recover_interrupted()` at start-up, `SearchPage.load_options()`, `app/services/updater.py` + `widgets/update_dialog.py` (GitHub latest release, asset `GeoHarvest-vX.Y.Z-windows.zip`, SHA-256 check, since 0.1.2 it hands over to `GeoHarvest-Setup.exe --update`, see the Release row in Decisions; only when frozen), Settings (speed Gentle 2 / Normal 4 / Fast 8 parallel searches, updates, data folder, delete all, fair-use note), styled spin box arrows
- [x] **7. Release**: `tools/build.py` (PyInstaller one-folder, unused Qt/numpy/PIL/lxml/cryptography left out: 38 MB zip, then runs `GeoHarvest.exe --self-test`), `.github/workflows/build.yml` (tests + build on every push; on a published release it attaches the zip), `tools/screenshot.py` (README screenshots from fictional demo data in a throwaway data folder), full README, release notes in `docs/releases/v0.1.0-beta.md`. The GitHub release itself is published by the user

## Log, oldest first

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
- 2026-10-16: v0.1.2 beta handed to testers. Waiting for feedback; see "Where things stand".
- 2026-10-17: v0.1.3 beta, first tester feedback. Setup root cause: it copied the whole folder it
  ran from (a tester's Downloads, with an Office installer) into `uninstall\` -> slow "Finish up",
  then disk full; and Cancel had already deleted the old `_internal`, so the app wouldn't start.
  Fixed (staged install, own files only). Zip 41 -> 32 MB. Search page: suggestion written twice
  (Qt writes the completion in on highlight; the trailing ", " made the click append it again),
  cities start unticked, "At least"/"Stop after" aligned, "Details to include". Leads: detail
  popup, delete leads, opens on the latest search; Past searches > Load with a toast. Tested:
  Setup into a test folder from a folder holding a 300 MB unrelated file (3 s, uninstaller 16 MB),
  cancel mid-copy keeps the previous version with no leftovers, packaged self-test and GUI start,
  completer driven by keyboard and mouse (the old code reproduced the bug), UI smoke test with
  demo data. Not tested: a real default-folder install over a broken 0.1.2.
- 2026-10-17: v0.2.1 beta, the user's answers to the feature questions (see "Decided"
  rows above): search around a place, max rating/reviews, website any/has/none, four opening-hours
  switches, owner's name + LinkedIn search link, Leads > Columns, CRM CSVs + Copy for Google
  Sheets, proxies, switches instead of tick boxes. Tested: 27 unit tests; live area search
  (Dubai Marina 3 km, then a 2 km run through the real ScrapeWorker with owner lookup: 15 leads,
  all inside the circle and matching the filters, 13 s); Google searches through local HTTP and
  SOCKS5 proxies; UI smoke tests with screenshots; packaged self-test (now also SOCKS + time
  zones) and GUI start. Not tested: real paid proxies, the CRM files imported into the real CRMs,
  and Open now across many time zones.
- 2026-10-17: Milestone A of the next version (three-step search). Root cause of "400 asked, 115
  given": all 150 searches ran, and the place ran dry under website + phone + **Startups**
  (most UAE agencies are older or their age is unknown); the tile went up and down because
  leads were saved, then deleted by the age check. Also found: the user's 5th business type was
  a stray "a". Tested: 30 unit tests (balance across cities, drop reasons, delete-then-resume,
  quality score, hidden addresses); live run in the real window (offscreen): digital marketing
  agencies in Dubai + Ajman, Startups, stop after 40: steps 1-2-3 in order, website checks
  topped up from 60 to 141 as the age filter dropped leads, 26 of 40 picked with the reasons
  shown and both widen buttons. Not tested: the widen buttons clicked live, Smart mode with a
  real key in the new flow, a big multi-country run.
- 2026-10-17: Milestone B: business-type picker, select buttons for Details to include and
  Columns, unknown company ages kept. Tested: 30 unit tests; the picker driven in the real window
  (offscreen, dark theme): opens on focus, typing narrows it, Enter adds an own type, clicks add
  and remove while the list stays open (it closed after one click before the focus-proxy fix),
  Esc closes; details buttons change the saved fields; README screenshots refreshed (rendered
  offscreen with `QT_QPA_PLATFORM=offscreen QT_QPA_FONTDIR=C:/Windows/Fonts`, no window
  shown). Not tested: the picker with a real mouse and keyboard on the user's machine.
- 2026-10-17: Milestone C: LinkedIn from the website, "N/A" when not linked. Tested: 31 unit
  tests; 20 live Dubai agencies (16 company pages, 1 owner profile, the right person). Seen
  but not fixed (older code): `find_owner` gave "Middle East Golf" and "Code Quality" as owner
  names on 2 of those 20 sites.
- 2026-10-17: v0.2.2 beta: milestones A-C released as one version (`APP_VERSION`, notes in
  `docs/releases/v0.2.2-beta.md`).
- 2026-10-17: README rewritten in typencut's style with 10 new screenshots, MIT LICENSE, third-party
  notices and license files bundled in the download (PyQt6 is GPL v3), PRIVACY, DISCLAIMER and
  SECURITY pages, Settings > About. On-screen "tick" wording changed to match the switches.

- 2026-10-29: v0.3.0 milestones 1+2 (one commit: the form and the worker share the new
  options). 32 unit tests; live Dubai cafes run above. The loop was checked to end when website
  requirements leave most out (25 views, 33 of 500, shortfall shown). Not tested: the new form
  with a real mouse, a multi-city deep run, resuming a 0.2.2 search under the new rules.
- 2026-10-29: v0.3.0 milestone 3 (updates). Tested from source: Setup's GitHub lookup (0.6 s),
  `FetchJob` downloading, checking and unpacking the real v0.2.2 zip (6 s), and the Setup window
  going check -> download -> hand-over (v0.2.1 pretended). Not tested: the packaged app's
  download + countdown + Setup --update (needs a published release newer than the build).
- 2026-10-29: v0.3.0 milestones 4-7 (themes, resizing, Leads page, Settings and extras). Tested:
  offscreen renders of every page at wide and narrow widths; exporting marks leads (10 exported,
  50 left under "Not exported yet"); copy emails; the Sort button follows heading clicks;
  restore rebuilds the window with the data back; the tray notification only when the window
  is inactive. Not tested: the theme maker and dragging the menu order with a real mouse.
- 2026-10-29: v0.3.0 milestone 8 (languages): 475 strings in each of ar, de, es, fr, written by
  Claude. Tested: 51 tests (every page opens in every language, Arabic right to left), German
  and Arabic renders. Not checked by native speakers.
- 2026-10-29: v0.3.0 milestone 9: version, release notes, README, 10 new screenshots, 33 MB zip
  with a passing packaged self-test (20-lead live search). The install-if-blocked `.bat` moved
  to v0.3.1 (see roadmap.md). Handover split from one HANDOVER.md into `docs/handover/`.
