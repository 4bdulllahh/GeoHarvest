# Testers and feedback

What to do when the user or testers come back with problems, what usually causes them, and what has never been tested for real.

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
| "Not Responding" / the app closes while checking websites, mostly on older PCs (0.3.0 and older) | The email search on pages with pictures stored inside them. Fixed in 0.3.1, which also searches in batches of 100. Suggest Settings > Search speed > Gentle |
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
- Smart mode with real Gemini or Claude keys, and 0.3.1's opening lines, needs, best way to
  reach, deal-breakers, website text and answer language
- 0.3.1's batches on a large search (1,000+ leads) and on an older PC
- Searches from an EU IP
- Windows 10 (only built and run on Windows 11)
- Everything in "What the user should test in v0.2.2" above
