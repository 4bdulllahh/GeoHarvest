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

**Phase: beta testing (since 2026-10-16). Current version: v0.3.0 beta (2026-10-29).**
Version numbers follow the user's GitHub tags: keep `APP_VERSION` (app/config.py) equal to the
tag's numbers. Don't start new features unless the user asks.

v0.3.0 is pushed, with `docs/releases/v0.3.0-beta.md`, the README and fresh screenshots.
`dist/GeoHarvest-v0.3.0-beta-windows.zip` is built locally (packaged self-test OK). The user
publishes release `v0.3.0` and tests it. **Next agreed: v0.3.1**, a backup installer for Smart
App Control PCs (see [roadmap.md](roadmap.md)).

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

- Ask questions with the AskUserQuestion form, not as a text list.
- After every milestone: update the right file here (and [changelog.md](changelog.md)), commit,
  push, then ask before starting the next one.
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
