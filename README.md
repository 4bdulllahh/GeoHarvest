<p align="center">
  <img src="assets/logo-256.png" width="150" alt="GeoHarvest logo: a pitchfork driven through a folded map">
</p>

<h1 align="center">GeoHarvest</h1>

<p align="center"><b>Find business leads on Google Maps. Free, fast, and no API key needed.</b></p>

Tell GeoHarvest what kind of business you are looking for and where, and it collects every
match from Google Maps: name, phone, website, address, rating, reviews, opening hours and
more. It then visits each business's website to find **email addresses and social media
pages**, estimates **how old the company is**, and, if you connect an AI, **scores every lead**
against your ideal customer. Export the result to Excel in one click.

**Download:** [latest release](../../releases/latest) · **Version:** 0.1.2 (free beta) ·
**Works on:** Windows 10 and 11 · **Countries:** all of them

![GeoHarvest's Leads page: dental clinics with AI score, verdict and reason, phone numbers and more](docs/screenshots/leads.png)

> **Free while in beta.** Please [report anything confusing or broken](../../issues/new).

## Features

- **Any business, any country.** Type a niche (restaurant, dentist, real estate agency,
  consultancy...) or several at once. Tick the countries you want, including the whole
  **European Union** or the **Gulf (GCC)** in one click, then tick the cities. A country's
  biggest cities are ticked for you, and you can add any town that is not listed.
- **Fast.** GeoHarvest asks Google Maps for results directly instead of driving a web
  browser and clicking every listing, and it searches several cities at once. In testing it
  found 1,377 dentists across the Netherlands, the UAE and the US in 47 seconds.
- **More results per city.** Google's own map stops at about 120 places; GeoHarvest pages
  through to about 200 per city and business type.
- **Maximum detail on every lead.** Name, category, phone (local and international format),
  website, rating, number of reviews, address split into street, area, city, postal code and
  country, map coordinates, opening hours, price level, description, features (wheelchair
  access, women-owned...), whether the owner has claimed the listing, and links to the Google
  Maps page and its reviews.
- **Emails and social media.** GeoHarvest reads each business's website (the home page and
  its contact and about pages) and collects email addresses and Facebook, Instagram,
  LinkedIn, X, YouTube and TikTok links. It decodes hidden ("protected") emails and throws
  away template addresses such as `you@example.com`.
- **Startup or established.** Google Maps does not record when a company was founded, so
  GeoHarvest estimates it from when the business's website was registered, or first
  appeared online. Filter for **startups** (under 3 years) or **established** companies.
- **Filters.** Minimum rating, minimum number of reviews, must have a website, must have a
  phone number, leave out closed businesses, leave out businesses you found before, and stop
  after a number of leads.
- **Smart mode (optional).** Connect an AI and describe your ideal customer in plain words.
  The AI checks every business is genuine and gives it a score from 0 to 100, a verdict
  (Good fit, Maybe, Poor fit) and a one-line reason. It can leave out poor fits for you.
  Works with free AIs (Google Gemini, Groq, OpenRouter, Mistral), paid ones (Claude, OpenAI,
  DeepSeek) and **AI running on your own computer** (Ollama, LM Studio): free, private and
  fast on a good graphics card.
- **Live results.** Leads appear in the table while the search runs. Filter as you type,
  sort any column, double-click to open a business in Google Maps.
- **Excel and CSV export.** Only the columns that have data, links you can click, and safe
  against spreadsheet formula tricks hidden in business names.
- **Nothing is ever lost.** Every result is saved the moment it arrives. Stop a search, close
  the app, or have Google ask GeoHarvest to slow down, and **Resume** carries on exactly where
  it stopped.
- **Past searches.** Reopen the leads of any search, resume it, or run it again later.
- **Updates itself.** When a new version comes out, GeoHarvest offers to install it, checks
  the download is genuine, and keeps all your searches and settings.
- **Private.** Everything stays on your computer. Your AI key is encrypted so only your
  Windows account can read it, and is sent only to the AI provider you chose.
- **Easy to read.** Dark, light or match-your-computer themes, four text sizes, high contrast
  and bold text.

## How it works

![The New search page: tick countries and cities, with live progress tiles while a search runs](docs/screenshots/search-running.png)

1. **New search.** Type the kind of business. Tick the countries, then the cities. Pick a
   company age and any filters. Press **Start search**.
2. **Watch it work.** Tiles show leads found, cities searched, websites checked, emails found
   and (in Smart mode) leads scored by the AI. Press **Stop** whenever you like.
3. **Leads.** Filter, sort, and look through everything found. Right-click a row to copy a
   phone number or email, or open the website.
4. **Export.** Press **Export to Excel** (or CSV). The export contains exactly the rows on
   screen, in that order, so filter and sort first if you want a shorter list.

### Smart mode

![The Smart mode page: choose an AI, add a key, describe the ideal customer](docs/screenshots/smart.png)

1. Open **Smart mode** and choose an AI. **Google Gemini** is a good free start: press
   **Get a free key**, sign in with a Google account, copy the key and paste it in.
   For a free, private AI on your own PC, install [Ollama](https://ollama.com/download),
   run `ollama pull llama3.2`, and choose **Ollama (on this PC)**.
2. Press **Load models** and pick one.
3. Describe your ideal customer: what you sell, who buys it and who is not worth contacting.
4. Press **Save and test**. GeoHarvest asks the AI to score a sample business, so you know it
   works before a real search.
5. Tick **Smart mode** on the New search page. To score a search you already ran, open it on
   the Leads page and press **Score with AI**.

### Past searches and settings

![Past searches: open, resume, run again or delete any search](docs/screenshots/history.png)

**Settings** has the theme and text size, **search speed** (Gentle, Normal or Fast: faster
finishes big searches sooner but makes Google more likely to ask GeoHarvest to slow down),
the update check, your data folder, and **Uninstall**.

## Install

1. Download `GeoHarvest-vX.Y.Z-windows.zip` from the
   [latest release](../../releases/latest).
2. Right-click it and choose **Extract All** (Setup can't run from inside the zip).
3. Open the extracted folder, double-click **GeoHarvest-Setup.exe** and click **Install**.
   At the end, choose the Start menu entry, a desktop shortcut and whether GeoHarvest opens
   when Windows starts. No administrator rights needed.

**"Windows protected your PC"?** GeoHarvest is new and not yet code-signed (a signing
certificate costs money every year), so Windows SmartScreen does not recognise it. Press
**More info**, then **Run anyway**. You only need to do this once.

No account, no sign-in. Your searches, leads and settings are kept on your computer in
`%APPDATA%\GeoHarvest`, outside the app folder, so updating never loses them. To remove
GeoHarvest, use **Settings > Uninstall GeoHarvest** or Windows Settings > Apps; it asks
whether to keep your data.

## Good to know

- **Results per search.** Google shows about 200 businesses per city and business type. For
  more leads, tick more cities or add more business types (`dentist, dental clinic,
  orthodontist`).
- **"Google asked GeoHarvest to slow down."** Very large searches from one internet
  connection can hit Google's limits. GeoHarvest pauses, keeps everything found, and you can
  resume from Past searches after about 15 minutes. Choosing **Gentle** speed in Settings
  makes this less likely.
- **Company age is an estimate.** It is based on the website's domain. Some countries'
  registries (for example Pakistan's `.pk` and Germany's `.de`) do not publish registration
  dates; for those, GeoHarvest uses the first time the site appeared in the Internet
  Archive, which is slower, so it only does that when you filter by Startups or Established.
  Businesses without a website have no age.
- **Emails** come from the business's own website. Businesses that only have a Facebook or
  Instagram page get that link, but no email, because those sites block automated visits.
- **Use it fairly.** GeoHarvest reads public listings and public websites. When you contact
  the businesses you find, follow the rules where you and they are, such as GDPR in the EU
  and UK, CAN-SPAM in the US and the UAE's data protection law, and Google's terms of service.

## Run from source

```
git clone https://github.com/4bdulllahh/GeoHarvest
cd GeoHarvest
pip install -r requirements-dev.txt
python run.py                      # run the app
python -m pytest tests/ -q         # tests (no network needed)
python tools/build.py              # dist/GeoHarvest-vX.Y.Z-windows.zip (installer inside), self-tested
python tools/screenshot.py         # these README screenshots, from made-up demo data
```

Publishing a release on GitHub builds the zip and attaches it automatically
(`.github/workflows/build.yml`). [HANDOVER.md](HANDOVER.md) explains how everything works,
the decisions behind it, and where each feature lives.

## Milestones

| | Milestone | What it delivered |
|---|---|---|
| ✓ | 1. Shell | The window, theme, sidebar and logo, in the style of HomingPigeon |
| ✓ | 2. Search engine | Google Maps search without a browser, city by city, saved as it goes |
| ✓ | 3. Search and Leads | The search form, live table, filters, Excel and CSV export |
| ✓ | 4. Enrichment | Emails and social links from websites, company age |
| ✓ | 5. Smart mode | AI lead scoring with free, paid and on-your-PC AIs |
| ✓ | 6. History and updates | Past searches, resume, auto-update, settings, every country |
| ✓ | 7. Release | The Windows download, automatic builds, this README |

**Ideas for later:** more languages in the app, emails from Facebook pages, a map view of
results, scheduled searches, and a Mac version.
