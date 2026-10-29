# Roadmap

Before starting a new batch or a release, read this and ask the user whether to include any
open item. Move items to [changelog.md](changelog.md) when they ship.

## Next: v0.3.1, a backup installer for Smart App Control PCs

Agreed with the user on 2026-10-29 (they chose to ship 0.3.0 without it; READ ME FIRST and
the README say it's coming). Smart App Control on some Windows 11 PCs blocks every unsigned
program, with no "Run anyway".

HomingPigeon's `installer/install-if-blocked.bat` can't be copied as is. It only has to get
past Setup, because HomingPigeon runs on signed python.org Python. GeoHarvest's app is an
unsigned PyInstaller `GeoHarvest.exe`, which SAC blocks too. What it needs:

- A second install method: python.org Python + pip-installed `requirements.txt` + GeoHarvest
  from source, like HomingPigeon's `installer/setup_app.py` and `tools/build_installer.py`.
  The embeddable Python has no Tkinter, and GeoHarvest's Setup uses Tkinter.
- An update path for those installs that doesn't run `GeoHarvest-Setup.exe`.
- The `.bat` in the zip, plus the README and READ ME FIRST updated.

## Known issues

- `enrich.find_owner` returns junk names on some sites ("Middle East Golf", "Code Quality"
  on 2 of 20 Dubai agencies). Tighten `OWNER_PATTERNS` / `NOT_NAME_WORDS` with a test.
- Owner LinkedIn profiles are rare (1 of 20 in the live test) because only the website is used.
  More would need a search API key from the user (Brave Search was the option offered).
- Many .ae (and other) domains have no findable age, so age requirements rank lots of
  "Unknown" leads.
- Watch how long very large searches (400+ leads, 150 queries, deep rounds) take and whether
  Google rate-limits them.
- The translations were written by Claude and not yet checked by native speakers.

## Ideas for later

- Emails from Facebook pages (social sites block plain requests).
- A map view of results.
- A Mac version.
- Code signing, so SmartScreen and Smart App Control stop blocking Setup (costs money every year).
