# GeoHarvest: handover

For the next Claude session. The user starts it with **"continue read the handover"**: read
this file, check `git status` and `git log --oneline -5`, say in 2 or 3 lines where things
stand, then carry on with the next milestone. The plan below is already approved.

This file only says where we are. What the app is, how the code is organised and every past
decision are in [docs/handover/README.md](docs/handover/README.md): read that index, then
only the file for the part you are changing.

## Current plan: v0.3.3 beta, a faster and steadier search (approved 2026-11-16)

The user's answers: a search **keeps going to the maximum** (no early stop at the minimum);
Google's limit is avoided and recovered from inside the same run; updates download quietly,
then ask "Update now" or "Later"; ask before pushing; research and the audit go to a cheaper
model (model-router skill).

| # | Milestone | Size | Status |
| --- | --- | --- | --- |
| M1 | Repo setup: CLAUDE.md follows the global rules, this file | S | done |
| M2 | Research the GitHub scraping tools and audit the whole app (cheaper model). Report: [docs/handover/audit-2026-11.md](docs/handover/audit-2026-11.md) | M | done |
| M3 | Resume shows real numbers: Leads, Websites and Email tiles fill in at once (`search.tally`, `SearchPage._show_tally`) | S | done |
| M4 | Leads keep their exported marks and found dates (`search.set_picked` deletes and rewrites every batch) | S | |
| M5 | Shorter batches, leads appear live: a batch also ends after a set number of Google pages | M | |
| M6 | Faster saving: progress no longer rewritten in full after every page; parallel searches stay parallel to the end | M | |
| M7 | Similar business types: a warning when types overlap; searches that only bring known businesses are cut short | M | |
| M8 | Google's limit 1: slow down by itself when Google answers slowly | M | |
| M9 | Google's limit 2: on a limit, a short wait and carry on inside the same run ("Going slower for a moment") | M | |
| M10 | Internet drops: the search waits and carries on by itself | S | |
| M11 | Opening hours warning before starting, when the choices leave out most businesses | S | |
| M12 | Update later: "Update now" or "Later", no countdown; Later asks again next start | S | |
| M13 | Tidy up storage: "Free up space" in Settings, automatic clean-up of finished searches | M | |
| M14 | Audit group A: search screens (Run again while running, stale buttons, deleted search still shown) | M | |
| M15 | Audit group B: the search job never gets stuck, errors reach the log | M | |
| M16 | Audit group C: Leads page speed with 30,000 rows | M | |
| M17 | Audit group D: backups (restore, temp file then rename, off the UI thread) | M | |
| M18 | Audit groups E and F: exports, saved keys | M | |
| M19 | Audit groups G, H and I: Smart mode, website checks, Setup | M | |
| M20 | Release v0.3.3 beta | M | |

**Proposed to the user on 2026-11-16, not yet approved:** the M14 to M19 split above, and M7
gaining "split a map area into four only when Google returns a full list" (from the research)
in place of today's all-at-once grid. Ask before building either. The audit findings each
milestone fixes are listed under its heading in the audit file.

## What the user's real search showed (2026-11-16, read-only look at the database)

Search 12: 12 business types x 11 UAE cities, minimum 200, no maximum (so 600).

- Google listed 31,008 businesses, 390 fit (about 1 in 80). A batch ends only after 100 new
  ones fit, so one batch is about 400 Google pages with no new leads shown.
- 694 deeper map-view searches were added; 289 of them were part-way through at once.
- Left out: 16,140 for opening hours (Open now, 24 hours and weekends all on), 12,338 no website.
- The progress record is 130 KB and is rewritten after every page. The database is 142 MB
  (66,568 candidates, about 1.5 KB each).

## Current state

- **Last done:** M3. Resume fills the tiles from `search.tally` (one SQL count, also used by
  `_show_unfinished`, which no longer parses every candidate on the UI thread). Tested in
  `test_core.py` and against the user's real search (383 leads); **not clicked through in the
  running app**, because opening it would carry on the user's real search.
- **Next:** M4. Read `set_picked`, `check_candidate`, `delete_leads` in `app/core/search.py`
  and the M4 heading in the audit file.
- **Changelog:** `docs/handover/changelog.md` gets its v0.3.3 lines at the release (M20), from
  the milestone table above.
- **Open questions:** the backup installer for Smart App Control PCs was planned as v0.3.3.
  It moves to v0.3.4 unless the user says otherwise (told on 2026-11-16, no answer yet).
- **Known issues:** see [docs/handover/roadmap.md](docs/handover/roadmap.md).
- **Not pushed:** the M1, M2 and M3 commits.
