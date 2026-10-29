# Architecture

How GeoHarvest is put together: the files, the rules every change keeps, the window and its look. Decisions already made: don't re-ask them. Each row says what was chosen and why.

## Files

```
run.py                     launcher (crash guard, theme, window)
app/config.py              paths (%APPDATA%/GeoHarvest), version, repo URL
app/i18n/                  t() and the five languages' catalogs (see languages.md)
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

## Decisions

| Topic | Decision |
|---|---|
| UI toolkit | PyQt6, Fusion style, one app-wide stylesheet from `app/ui/theme.py` (copied from HomingPigeon) |
| Logo | A pitchfork driven *through* a folded map (user's choice, not a map pin). `assets/logo.svg`, rendered by `tools/make_icons.py` |
| App name | **GeoHarvest** (renamed from MapScout on 2026-10-16 to match the repo github.com/4bdulllahh/GeoHarvest; the local folder is still called MapScout). Data folder: `%APPDATA%/GeoHarvest` |
| Switches | Every QCheckBox and checklist item is drawn as an on/off switch by the stylesheet (`theme.switch_knob` SVGs), so pages still use `checkbox()`. **Except** "Details to include" and Leads > Columns (user, 2026-10-17: a switch beside each word was confusing): those use `common.select_button()`, a checkable button with the same isChecked/setChecked/toggled API, styled by `pick="on"/"off"` (selected = accent fill, unselected = greyed, selected but disabled = accent outline) |
| Themes and scrolling (0.3) | Copied from HomingPigeon: `app/core/themes.py` (8 presets, home-made themes in the `custom_themes` setting, files `.ghtheme`; files carry both `geoharvest_theme` and `homingpigeon_theme` keys so each app loads the other's), `widgets/theme_editor.py`, `theme.derive`/`use_theme` (a theme names 6 colours, the rest are mixed from them; `fill_*` tokens carry gradients), `app/ui/scrolling.py` (one app-wide filter: eased wheel scrolling, `smooth_scroll` setting, scrollbars marked `hot` widen). `MainWindow.show_theme` rebuilds when the font changes. Menu order and hidden pages: `prefs.ordered`, `nav_order`, `nav_hidden`; New search can't be hidden (`ALWAYS_SHOWN`). Reset appearance resets `prefs.APPEARANCE_KEYS`, keeps home-made themes |
| Resizing (0.3) | `widgets/common.Columns` puts parts side by side and stacks them below `stack_below` px (times the text scale): Countries/Cities at 720, rating/reviews sliders at 640. Button rows use `wrap_row`/`flow_row` (Search tiles, Leads toolbar, Settings theme buttons). Below 1000 px the sidebar shrinks to icons (`MainWindow._fit_sidebar`, `NavButton.set_compact`); the window can't go below 760 px. Window size and place are saved in the `window_geometry` setting (base64 of `saveGeometry`) |
| Settings and extras (0.3) | `core/backup.py`: SQLite backup API to a `.ghbackup` file (searches, leads, presets, settings; never the secrets file); restore keeps the current database as "Before restoring ..." in `DATA_DIR/backups`, then `theme.apply_preferences` + `MainWindow._rebuild`. Weekly `auto_backup` runs in a Task 20 s after start (`auto_backup`, `last_auto_backup` settings, keeps `AUTO_KEEP` = 4). `prefs.START_PAGES` + `last_page` (saved on every page switch); with `start_page` never set, a newcomer (no searches) opens on Start here. `prefs.DATE_FORMATS`/`TIME_FORMATS`, `format_date`/`format_datetime` used by History, the Leads picker and the date columns. Forget saved keys = `credentials.clear_all()` (AI keys and proxies). Report a problem opens GitHub issues/new. `pages/guide.py` (Start here, nav item last) ticks each step from the database. `MainWindow.tell_user`: only when the window is not active and `notify_done` is on: `QApplication.alert` + a tray message (the tray icon hides after 30 s); called when a search ends done, paused by Google or stopped by the AI, never on Stop. Presets: `search.presets/save_preset/delete_preset` in the `requirement_presets` setting, everything except `PRESET_SKIPS` (types and places); buttons after the Quick setup ones, right-click to delete. Estimate: `search.estimate` (120 listed per search, 6 s per search / parallel, 4 s per website visit / 16, half the listed have a website; shown as half to 1.5 times) |
