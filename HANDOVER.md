# GeoHarvest handover

Read this first when picking the work back up (person or Claude). It says what
is done, what is next, and the decisions already made so nobody re-asks them.

## Where things stand (start here)

**Phase: beta testing (since 2026-10-16). Current version: v0.2.2 beta (2026-10-17).**
All 7 original milestones are done, then v0.1.1-v0.1.3, v0.2.1 and **v0.2.2**. Version numbers
follow the user's GitHub tags: keep `APP_VERSION` (app/config.py) equal to the tag's numbers.
Don't start new features unless the user asks. Ask the user questions with the
AskUserQuestion form, not as a text list (their preference).

**v0.3.0 in progress (started 2026-10-29).** The user tested v0.2.2 and asked for a big batch.
Agreed plan (form answers), in order, pausing to ask after milestones 2, 3 and 8:
1. [x] Requirements: "Which businesses?" renamed Requirements, every choice a select button,
   min/max sliders (rating, reviews, company age in years with Any/Startups/Established/My own
   range quick buttons), Name can be unpicked (none picked = Name), new must-haves (email,
   social media, LinkedIn, owner, claimed, hours listed), Quick setup (Cold email / Cold calling /
   Build a database, `search.USE_CASES`)
2. [x] Finding pipeline: "Stop after" -> **Minimum leads**, every match kept best first, digs
   deeper by itself, asks before adding cities or related types; score = info found + a little
   reputation, low scores ranked last, breakdown in the lead window (see "Finding (0.3)" below)
3. [ ] Updates: no switch; check + download latest on open, install right away unless a search
   runs; Setup (0.3+) fetches the newest release instead of installing an old one, offline it
   installs what it has; Settings > Updates = version + Check now + GitHub page
4. [ ] HomingPigeon look: themes + theme maker + share file, smooth scrolling, menu order/hide,
   reset appearance
5. [ ] Resizing: rows wrap, side-by-side parts stack, sidebar shrinks to icons below ~1000 px,
   remember window size and place
6. [ ] Leads page: Sort menu, Show menu, date range, rating/reviews sliders, copy emails/phones,
   export only new leads, export for HomingPigeon, score breakdown (done in 2)
7. [ ] Settings/extras: backup + restore + weekly auto backup (keep 4), first page on open,
   date/time format, forget saved keys, report a problem, Start here guide page, notify when a
   search finishes, requirement presets, live estimate on the form
8. [ ] Languages: Arabic (RTL), German, Spanish, French via HomingPigeon's i18n package; Claude
   writes the translations
9. [ ] Build v0.3.0 zip (+ install-if-blocked .bat), release notes, README

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

**Known issues, candidates for the next version:**
- `enrich.find_owner` returns junk names on some sites ("Middle East Golf", "Code Quality"
  on 2 of 20 Dubai agencies). Tighten `OWNER_PATTERNS` / `NOT_NAME_WORDS` with a test.
- Owner LinkedIn profiles are rare (1 of 20 in the live test) because only the website is used.
  More would need a search API key from the user (Brave Search was the option offered).
- Many .ae (and other) domains have no findable age, so Startups/Established rank lots of
  "Unknown" leads.
- Very large searches now run every city to its share before checking websites: watch how
  long a 400-lead, 150-query search takes and whether Google rate-limits it.

**When the user comes back with feedback:**

1. Collect it from what they paste and from GitHub issues
   (https://github.com/4bdulllahh/GeoHarvest/issues). Sort it into bugs (crashes, wrong or
   missing data, things that don't work), confusing screens or wording, and feature
   requests. Show the user the sorted list and agree what goes in the next version before
   writing code.
2. Bugs: reproduce first, then fix the root cause. Add a test in `tests/test_core.py` for
   anything in `app/core/` or `app/workers/`. Read the "Decisions" table below before
   changing behaviour; it records why things are the way they are.
3. Ship the batch as one release (see "Releasing a new version" at the bottom). The
   user always wants a paste-ready paragraph for the GitHub release description. Write it
   in plain English for testers, not developers.
4. Follow the working agreement: update the Log here, commit, push, then ask before
   starting the next batch.

**Where testers' problems usually come from:**

| They say | Likely cause |
|---|---|
| Setup failed at "Finish up" with "not enough space on the disk" (0.1.2 only) | 0.1.2's Setup copied the whole folder it ran from (often Downloads) as the uninstaller. Fixed in 0.1.3, whose Setup also deletes that bloated `uninstall` folder |
| Setup won't open, or a "Failed to load Python DLL" error | They ran `GeoHarvest-Setup.exe` from inside the zip. Extract it first (READ ME FIRST.txt says so). |
| "Windows protected your PC" | The app isn't code-signed. More info > Run anyway. |
| Setup says files are missing, or the app vanished | Antivirus quarantined something. Ask which antivirus they use. |
| "Google asked GeoHarvest to slow down" | Google rate-limited their connection (`scraper.Blocked`). Wait 15 min, resume, use Gentle speed. |
| Few or no results in the EU/UK | Google's consent page. The `CONSENT`/`SOCS` cookies were never tested from an EU IP. |
| Smart mode errors with Gemini or Claude | Never tested with a real key (only a fake OpenAI-style server). Check `app/core/ai.py` reply parsing. |
| No emails for many leads | Normal for businesses with only Facebook or Instagram (those block plain requests), or with no website. |
| Update now didn't work | 0.1.0 and 0.1.1 can't update to 0.1.2 by themselves. Install 0.1.2 by hand once. |
| "I asked for 400 and got fewer" (0.2.2+) | Read the summary under the tiles: it lists why businesses were left out (`search.dropped_counts`). Usually the places are too small for the filters; the widen buttons help |
| "LinkedIn says N/A" | Normal: the business's website doesn't link a LinkedIn page or profile. LinkedIn and free search engines block automatic lookups |
| Address "Service area (address hidden on Google)" | Normal: the business hides its address on Google. "Must show its address" leaves these out |
| Company age "Unknown" | The domain registry hides the date and the Internet Archive had nothing. Kept on purpose, ranked last |

**Logs to ask testers for:**
- app crashes: `%APPDATA%\GeoHarvest\logs\crash.log`
- Setup problems: `%TEMP%\GeoHarvest-setup-log.txt` (Setup's "Open log file" button opens it)

**Never tested for real** (watch for these in feedback):
- Setup installing into the default folder over an Inno-installed 0.1.1
- 0.1.1's updater running the new Setup (the `/SILENT` path)
- Smart mode with real Gemini or Claude keys
- Searches from an EU IP
- Windows 10 (only built and run on Windows 11)
- Everything in "What the user should test in v0.2.2" above

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
| Release | GitHub Releases, `GeoHarvest-vX.Y.Z-windows.zip` holding `GeoHarvest-Setup.exe`, its `runtime/` folder and `READ ME FIRST.txt` (since 0.1.2; must be extracted first). **Own installer** `installer/setup_app.py`: Tkinter, standard library only, copied from HomingPigeon's (`Email-Sender/installer/setup_app.py`) for the look (welcome card, step list with ticks, progress bar, activity log, finish page with Start menu / Desktop / open-at-Windows-start (unticked) / open-now). PyInstaller one-folder with `--contents-directory runtime`, never one-file (HomingPigeon's one-file Setup was flagged by Defender as Wacatac). Carries the app folder as `payload.zip` (LZMA), unpacked into `<install>.new` and swapped in only when complete (old files go to `<install>.old`, and are put back if the swap fails), so Cancel and a full disk never leave a half-install; Cancel is ignored once the swap starts. Installs per user to `%LOCALAPPDATA%\Programs\GeoHarvest` (no admin), writes `version.txt`, keeps a copy of itself (only `GeoHarvest-Setup.exe` and its `runtime` folder minus the payload, never the folder it was run from) in `<app>\uninstall\` as the uninstaller, registers HKCU `...\Uninstall\GeoHarvest`. The app's Update now runs `GeoHarvest-Setup.exe --update --target <app folder>` directly (no batch file, no console; `PYINSTALLER_RESET_ENVIRONMENT=1`); Setup waits for the app to close, updates, reopens it. Settings > Uninstall asks keep/delete data in the app, then runs `uninstall\GeoHarvest-Setup.exe --uninstall --confirmed [--delete-data]`. Setup also accepts 0.1.1's Inno-style `/SILENT /DIR=` and removes 0.1.1's Inno registry entry and `unins000.*`. Version check compares numbers only (tags are written with and without "beta"). No accounts, everything local |
| Minimum leads (0.3) | Replaces "Stop after" (old `max_results` -> `min_leads`, converted in `options_with_defaults`). User's choice: **minimum, and keep every match found**, best score first. "Leave out businesses I found in earlier searches" is on by default since 0.1.1 |
| Finding (0.3, replaces the 0.2.2 "three-step search") | `workers/scrape.py` runs **rounds** of: 1. Search Google (every listing into `candidates`, `dropped` = `search.why_not`), 2. check every fitting website best first (`search.why_not_checked`: age range, email, social media, LinkedIn, owner), 3. Smart mode AI on everything left. `keep()` then makes every fitting candidate a lead (`set_picked`), sorted checked first, known age first, then `search.score`. If fewer than the minimum: next round runs the queries capped at their share (first round: share of 3N, `POOL`) to the end, then `search.deep_queries` splits each city search that Google gave >= 100 for (`DEEP_AT`) into map views (`geo.radius_cells` around the median of its businesses, radius = 80th percentile distance, 2-15 km), cities taking turns; deep rounds stop starting queries once they have 3x what is still missing (the rest wait). Stops when nothing is left or a round makes no progress (failing queries). User's choice: digging deeper is automatic; adding cities or related types (`search.RELATED`, `related_types`) is a button after the shortfall summary. Live 2026-10-29: Dubai cafes with a phone, minimum 300: 630 leads in 52 s (36 views planned, 4 needed); 0.2.2 found ~100. `balanced` and `enrich.age_mismatch` are gone |
| Score (0.3) | User: "whatever is most functional". `search.quality_parts`: mostly info found (email 15, phone 12, website 10, owner 8, socials 8, LinkedIn 4, address 6, claimed 5, hours 4, age known 4, description 4) + reputation (rating 8, reviews 12). Low scores are ranked last, never dropped (user's choice). The lead window (double-click) shows the breakdown |
| Requirements UI (0.3) | User's choice: **select buttons for every choice** in Requirements and Extra detail (switches stay only in the country/city checklists). Sliders: `widgets/range_slider.py` (HomingPigeon's, generalised to a step table): rating 0 (Any) to 5.0, reviews 0 to "No maximum" (`NO_MAX`), company age 0-30+ years (`age_min`/`age_max`, -1 = none; old `company_age` converted via `search.AGE_PRESETS`). A website-only requirement switches "Visit each website" on; switching that off clears them |
| Hidden addresses (2026-10-17) | Service-area businesses hide their address; Google sends only a rough pin (one was in Europe for a Dubai search). `places.parse` sets the address to `places.SERVICE_AREA`; `scraper.near_place` fills city and country from the query when the pin is within 50 km of where Google centred the city, else no country, which the country filter drops. Optional filter `require_address` ("Must show its address"). In the user's DB 82 of 227 leads were like this |
| Download size | 41 MB -> 32 MB in 0.1.3. `tools/build.py` leaves out the anthropic SDK's optional extras that PyInstaller pulled in (pygments, rich, click, aiohttp, Google auth, setuptools...: `EXCLUDE`), unused Qt DLLs and plugins (`DROP`; Qt6Svg and the svg plugins stay because the theme's tick and arrow icons are SVG), and Setup's unused SSL, Tcl time zones and translations (`SETUP_EXCLUDE`, `SETUP_DROP`). `run.py --self-test` sends a request through the SDK to prove it still works without them. What's left: Qt ~16 MB, Python twice (app + Setup) ~5 MB, the anthropic SDK ~5 MB (calling Claude over plain httpx would save that, but the claude-api guidance is to keep the SDK unless the user asks). HomingPigeon's 12 MB zip is not comparable: it ships source and downloads Python + PyQt6 during install |
| Columns ("Details to include") | `fields` option: the columns a search shows and exports (default all). Leads always store everything; the Leads page hides columns not in the selected search's `fields`, and export writes only the columns on screen (`exporter.export(..., keys)`). Website-only details (emails, socials, age) are greyed out when "Visit each website" is off. Every `places.FIELDS` key must be listed in `DETAIL_GROUPS` in `pages/search.py` |
| Cities | Since 0.1.3, ticking a country ticks **none** of its cities (user's request); the "ticks its biggest N" spin box is gone. `city_count` stays in options only for searches saved before city ticks |
| Leads page | Opens on the newest search, and switches to a search when it starts. Double-click opens `LeadDialog` (every filled field, links, Copy all, Open in Google Maps). Delete key, right-click or "Delete selected" removes leads (`searches.delete_leads`): from the selected search, or from every search when "All searches" is picked. Past searches > **Load** selects the search on the Leads page and shows a toast without leaving the page |
| AI keys | **No built-in API key anywhere** (user's explicit rule, 2026-10-17). Every provider uses only the key the user enters on the Smart mode page, stored DPAPI-encrypted. The only `api_key=` literal is `run.py`'s self-test sending "test" to a closed local port. Keep the official `anthropic` SDK (user said keep it; it costs ~5 MB) |
| Search around a place (0.2.1) | Options `where` = cities / area, `area_place`, `area_km`, `area_lat/lng`. The place is found with `scraper.locate()` (Google centres the map on it) when Start is pressed, and the point is saved in the options so resume/run again don't look it up again. `geo.radius_cells` covers the circle with map views at most 5 km wide (max 8 x 8); each query is "niche near Place @lat,lng,camera" and `scraper.search` sends only the niche with the map put there. Camera distance = view size / 0.23 (measured). Google pages outward past the view, so paging stops at the first page with nothing inside the view (measured: 102 s -> 7 s for 3 km, 111 -> 109 leads). `passes()` keeps only leads inside the circle; the country filter is off in area mode |
| Filters added 0.2.1 | `max_rating` (0 = none), `max_reviews` (-1 = none; 0 means no reviews), `website` any/yes/no (replaces `require_website`, converted in `options_with_defaults`), opening hours `open_now`, `open_24h`, `open_weekends`, `open_at` + `open_day` (0 = Monday) + `open_time`. Hours are parsed from Google's English text in `core/hours.py`, in the lead's own time zone; leads without hours are left out while any hours filter is on. Not wanted (user said no): exclude keywords, unclaimed-only, language choice, dedupe by phone/website, email verification, review text, notes/tags, scheduling. Deleted leads can come back in later searches (user's choice) |
| Owner's name (0.2.1) | Optional (`find_owner`, needs "Visit each website"). `enrich.find_owner`: schema.org "founder", then "Founder: Name" / "Name, Owner" / "founded by Name" in page text (role words in EN/DE/FR/ES), rejecting heading words. Else the RDAP registrant unless hidden for privacy. `owner_linkedin` (since 2026-10-17) is a linkedin.com/in/ profile the website links (`enrich.find_profiles`): the one whose address has the owner's surname, else the only one, else `places.NOT_FOUND` ("N/A"); a profile given as the Maps website counts too. The company `linkedin` column is a /company/ or /school/ link from the site, else "N/A" (only when the site was crawled). **A web search for profiles was tested and dropped** (2026-10-17, from the UAE): DuckDuckGo html/lite answer 202 bot challenges, Bing serves junk results to scripts, Startpage captchas, Brave 429, Yahoo 500, Ecosia 403, Mojeek has no LinkedIn profiles; searching Google itself would risk rate-limiting Maps. User chose website-only. Live, 20 Dubai agencies: 16 company pages, 1 owner profile. `quality` and CRM exports treat "N/A" as empty. Columns `owner_name`, `owner_source`, `owner_linkedin`. Live: 1 of 15 Dubai dentists had a name, so expect few |
| Exports (0.2.1) | Leads page "More exports": CSV, CSV for HubSpot / Pipedrive / Zoho CRM / Salesforce (`exporter.CRMS`: each CRM's company/account column names), "Copy for Google Sheets" (tab-separated text on the clipboard + opens sheets.new; values starting with = + - @ get a leading ' so Sheets keeps them as text). A direct Google Sheets upload was rejected: it needs OAuth and a Google Cloud project |
| Proxies (0.2.1) | Settings > Proxies: one per line (host:port, user:pass@host:port, host:port:user:pass, http/https/socks5/socks5h://), saved encrypted (`credentials`, name "proxies"), "Test them" checks each against google.com/generate_204. Only Google Maps searches use them (`MapsClient` keeps one httpx client per proxy and takes turns; a proxy that is limited or doesn't answer is skipped; `Blocked` only when none worked and at least one was limited). Website visits and AI go direct. Needs `httpx[socks]` (socksio, bundled); the self-test checks it. Tested live through local HTTP and SOCKS5 proxies |
| Switches | Every QCheckBox and checklist item is drawn as an on/off switch by the stylesheet (`theme.switch_knob` SVGs), so pages still use `checkbox()`. **Except** "Details to include" and Leads > Columns (user, 2026-10-17: a switch beside each word was confusing): those use `common.select_button()`, a checkable button with the same isChecked/setChecked/toggled API, styled by `pick="on"/"off"` (selected = accent fill, unselected = greyed, selected but disabled = accent outline) |
| Business types (2026-10-17) | `widgets/type_picker.py` `TypePicker`: the text box (still a comma list, the source of truth) plus a grouped list of `BUSINESS_TYPES` in columns that opens below on focus or click, narrows to what is typed after the last comma, adds/removes on click, Enter adds an unlisted type, Esc or leaving the box closes it. The list's buttons are NoFocus and the picker is ClickFocus with the box as focus proxy, so a click doesn't move focus to the page's scroll area (which closed the list after one click). Replaced the old comma-list completer |
| Columns after a search | Leads page "Columns..." opens `ColumnsDialog` (select buttons grouped like New search, `places.FIELD_GROUPS`; every FIELDS key in exactly one group, tested). Saves to the search's `fields` (`searches.set_fields`) or, for All searches, setting `all_searches_fields` |
| License and legal (2026-10-17) | Code is **MIT** (`LICENSE`, "Copyright (c) 2026 Abdullah", same as typencut). **PyQt6 is GPL v3**, so the Windows download as a whole is distributed under GPL v3: `tools/build.py` `add_legal_files()` puts `LICENSE.txt`, `THIRD-PARTY-NOTICES.md` and every bundled library's own license (`licenses/<package>/`, found by walking requirements.txt's dependencies, plus Python's `LICENSE.txt`, which covers OpenSSL, SQLite and Tcl/Tk) in the app folder and the zip root; Settings > About shows the notice GPL v3 asks interactive programs to show, with "Open the licenses". `PRIVACY.md` (what is stored and sent where: keep it true when adding a network call), `DISCLAIMER.md` (acceptable use, GDPR/CAN-SPAM, estimates, no warranty, not affiliated with Google), `SECURITY.md` (private reporting via GitHub's Security tab). GeoNames data needs its CC BY 4.0 credit (in the notices). If the user ever wants the whole download permissive, the route is PySide6 (LGPL) instead of PyQt6 |
| README | Laid out like the user's typencut README (centred logo, pitch, badges, hero shot, long Features list, 2-up screenshot tables, Privacy, Principles, Tech stack, How a search works, Roadmap, Legal, License). Screenshots come from `python tools/screenshot.py` (fictional demo data in a throwaway data folder; documentation-only proxy addresses); refresh them whenever a page changes |
| Languages | English only for v0.1. `app/i18n.py` is a pass-through `t()` so HomingPigeon's translation system can drop in later |

## Milestones

- [x] **1. Shell**: window, sidebar, theme, logo, settings storage (`app/core/db.py`), placeholder pages, Settings appearance controls, this file, README outline
- [x] **2. Scraper engine**: `app/core/scraper.py` (HTTP client + paging), `app/core/places.py` (Google's arrays -> lead dict, `FIELDS` = column order), `app/core/search.py` (options, queries, filters, saving, resume progress), `app/core/geo.py` + `app/data/cities.json` (244 countries, top 60 cities, built by `tools/build_cities.py`), `app/workers/scrape.py` (`ScrapeWorker`: parallel queries, saves every page, `stop()`, Blocked handling), `tests/test_core.py`
- [x] **3. Search and Leads pages**: `pages/search.py` (form remembers last options in setting `last_options`, comma-list autocomplete for niches and cities, live stat tiles, Stop, Open leads; `run(search_id)` also resumes), `pages/leads.py` (search picker, instant filter, sort, hides empty columns, reloads when a search picks its leads, right-click copy/open, delete search), `widgets/leads_model.py`, `core/exporter.py` (xlsx + csv, only used columns, formula-injection safe)
- [x] **4. Enrichment**: `app/core/enrich.py` (`Enricher`: home page + up to 3 contact/about pages, 2 MB cap per page, emails incl. Cloudflare-obfuscated and HTML-entity ones, own-domain emails first, socials; social pages given as "website" are filed under that network and not crawled; RDAP + Wayback age). Runs as step 2 of `ScrapeWorker` in a 16-thread pool (since 2026-10-17; it used to run alongside the search). Lead key `enriched` marks done, so resume re-checks only the rest
- [x] **5. Smart mode**: `app/core/ai.py` (providers, prompt, batch of 8 leads per request, tolerant JSON parsing, 429 wait-and-retry, fatal vs skippable errors, `test()` scores a sample lead), `app/workers/ai.py` (`AIScoreWorker`: Leads page "Score with AI"; during a search the AI runs in step 3 of `ScrapeWorker`), `pages/smart.py` (provider buttons, key, address for local/custom, model + Load models, ideal customer text, "leave out below N", Save and test, Turn off). Verdict comes from the score in code: 80+ Good fit, 50-79 Maybe, else Poor fit. A fatal AI error leaves the search `stopped` so resume re-scores
- [x] **6. History, resume, updater, Settings**: `pages/history.py` (open leads, resume, run again, delete), `search.recover_interrupted()` at start-up, `SearchPage.load_options()`, `app/services/updater.py` + `widgets/update_dialog.py` (GitHub latest release, asset `GeoHarvest-vX.Y.Z-windows.zip`, SHA-256 check, since 0.1.2 it hands over to `GeoHarvest-Setup.exe --update`, see the Release row in Decisions; only when frozen), Settings (speed Gentle 2 / Normal 4 / Fast 8 parallel searches, updates, data folder, delete all, fair-use note), styled spin box arrows
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
  geo.py                   countries and cities from app/data/cities.json; distance, radius map views
  hours.py                 opening hours text -> open now / 24 hours / weekends / a day and time
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

## Releasing a new version

1. Bump `APP_VERSION` in `app/config.py` to the numbers of the tag you will publish (e.g. "v0.2.2 beta"
   for tag v0.2.2; if they differ, installed copies keep offering the same update); write `docs/releases/<tag>.md`.
2. Commit and push; check the Actions run is green.
3. On GitHub: Releases > Draft a new release, tag `v0.2.0` or `v0.2.0-beta` (only the
   numbers are compared, so either works), paste the notes, Publish. The workflow attaches `GeoHarvest-v0.2.0-beta-windows.zip` within
   about 5 minutes; every installed copy then offers the update on its next start.

## Working agreement

After every milestone: update this file, commit, push, then ask the user before starting the next one.
