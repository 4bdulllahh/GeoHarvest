# GeoHarvest: notes for Claude

A free PyQt6 Windows app that finds business leads on Google Maps (repo
github.com/4bdulllahh/GeoHarvest; the local folder is still called MapScout). For
non-technical users: plain words on screen, in five languages.

**Read [docs/handover/README.md](docs/handover/README.md) first, then only the handover file for
the part you are changing.** Don't read every file: the table there says which one you need.

## Rules that are easy to break

- **No built-in API key anywhere.** Keys come only from the user, stored DPAPI-encrypted.
- Nothing slow on the UI thread: network, websites, AI and exports go through `app/workers/`.
- `app/core/` never imports PyQt. Business rules live there and are tested in `tests/test_core.py`.
- **Every new or changed piece of on-screen text needs translating** into ar, de, es and fr, or
  `tests/test_i18n.py` fails. See [docs/handover/languages.md](docs/handover/languages.md).
- Text with a value in it is a template, `t("{count:,} leads", count=n)`, never an f-string.
- New pages are imported lazily: add them to the hidden imports in `tools/build.py`.
- Every `places.FIELDS` key must be in exactly one `places.FIELD_GROUPS` group (tested).
- Users update in place and keep their data: old saved options are converted in
  `search.options_with_defaults`, never dropped.
- Commit and push at the end of each milestone, then ask before the next one.
- **Every request: review and ask first, build only after the user's thumbs up**, then commit,
  push, version bump + zip, release notes, docs and README screenshots. The steps are in
  "Working with the user" in [docs/handover/README.md](docs/handover/README.md).

## Everyday commands

```
python run.py                 # run the app
python -m pytest tests/ -q    # all tests, headless
python tools/build.py         # the release zip + self-test
```
