# Handover: start here

Notes for whoever works on GeoHarvest next, person or Claude. Read this page, then **only the
file for the part you are changing**. Each file records what was decided and why, so nobody
re-asks.

| File | Read it when you change |
|---|---|
| [architecture.md](architecture.md) | the file layout, threads, the window, themes, resizing, Settings, backups, notifications |
| [search.md](search.md) | New search, Google Maps, places, requirements, minimum leads, the quality score, websites, owners, proxies |
| [leads.md](leads.md) | the Leads page, Show and Sort, columns, exports and CRM files |
| [smart-mode.md](smart-mode.md) | the AI providers, keys and scoring |
| [languages.md](languages.md) | **any text on screen** (every string needs ar, de, es, fr) |
| [releasing.md](releasing.md) | Setup, updates, the download, licences, the README, publishing a version |
| [testers.md](testers.md) | feedback from the user or testers: common causes, logs, what was never tested |
| [roadmap.md](roadmap.md) | what is planned next and the known issues; check before a new batch |
| [changelog.md](changelog.md) | what went into each version and how it was tested (long: read only the part you need) |

## Where things stand

**Phase: beta testing (since 2026-10-16). Current version: v0.3.4 beta (2026-11-16, a one-fix patch of v0.3.3).**
Version numbers follow the user's GitHub tags: keep `APP_VERSION` (app/config.py) equal to the
tag's numbers. Don't start new features unless the user asks.

v0.3.3 (leads while the search runs, adaptive digging, Google's limits and lost connections
waited out inside the run, form warnings, an update notice that asks) and v0.3.4 (Resume
showing again after opening the app) are published on GitHub by the user. **In progress:
v0.4**, the audit fixes: M13 to M16 are done and pushed, M17 to M19 and the release are left
(see [../../handover.md](../../handover.md) and the v0.4 lines of [changelog.md](changelog.md));
the backup installer for Smart App Control PCs has no version number yet (see [roadmap.md](roadmap.md)).

## The product

A free Windows desktop app (Python + PyQt6) that finds business leads on Google Maps, like
omkarcloud's google-maps-scraper but faster and easier to use, for cold email, cold calling or
building a database. The user picks business types and places (countries and cities, or around
a place), sets requirements and a minimum number of leads, and gets every matching business
with maximum detail (phone, website, emails, social media, owner, company age...), exported to
Excel, CSV, CRMs or HomingPigeon. Two modes:

- **Quick mode**: search only.
- **Smart mode**: the user adds their own AI key (or a local model) and the AI scores each lead
  against the user's description of an ideal customer.

Nothing paid: no paid APIs, no proxies to buy. No accounts; everything stays on the user's
computer. The UI copies HomingPigeon (https://github.com/4bdulllahh/HomingPigeon,
local folder `../Email-Sender`): same theme module, sidebar, cards, status bar, worker pattern.

## Working with the user

**How every request goes** (the user's global workflow, since 2026-11-16; it replaced the
2026-10-30 process, which pushed without asking). When they finish writing a batch of fixes
and features:

1. Go through every item and read the code it touches. Play the prompt back: a numbered
   summary, what you found and recommend, and "did you miss anything?". No code yet.
2. After the thumbs up: questions with the AskUserQuestion form, then the milestone plan as a
   table. Wait for the final thumbs up.
3. Build one milestone at a time, with tests. After each: update the right file here (and
   [changelog.md](changelog.md)) and [../../handover.md](../../handover.md), commit locally
   (`feat: ...`, `fix: ...`, `docs: ...`), report, ask for the usage %, and ask before the next one.
4. **Ask before pushing**: one question listing the commits. Never force push.
5. The release milestone: bump the version (`APP_VERSION`), build the zip
   (`python tools/build.py`), write release notes (`docs/releases/<tag>.md` plus a short
   paste-ready paragraph), update every md file that needs it (this folder, changelog,
   roadmap...) and the GitHub README with fresh screenshots (`python tools/screenshot.py`).

- Ask questions with the AskUserQuestion form, not as a text list.
- For every release the user wants release notes in `docs/releases/<tag>.md` plus a short
  paste-ready paragraph, in plain English for testers.

## Commands

```
pip install -r requirements-dev.txt
python run.py                 # run the app
python -m pytest tests/ -q    # tests
python tools/i18n.py check    # every language has every string
python tools/screenshot.py    # refresh README screenshots (demo data)
python tools/build.py         # dist/GeoHarvest-vX.Y.Z-windows.zip (installer inside) + self-test
python tools/make_icons.py    # after editing assets/logo.svg
```
