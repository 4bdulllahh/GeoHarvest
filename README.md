<p align="center"><img src="assets/logo-256.png" alt="GeoHarvest logo: a pitchfork driven through a folded map" width="110" /></p>

<h1 align="center">GeoHarvest</h1>

<p align="center"><b>Find business leads on Google Maps. Free, fast, and no API key needed.</b></p>

Tell GeoHarvest what kind of business you want and where: whole countries city by city, or
everything within a few kilometres of an address. It collects every match from Google Maps,
with name, phone, website, address, rating, reviews, opening hours and more. Then it visits
each business's website for **email addresses, social media and the owner's name**, estimates
**how old the company is**, and, if you connect an AI, **scores every lead** against your ideal
customer. Export to Excel, to your CRM, or straight into Google Sheets. No account, no
subscription, nothing to pay: everything runs on your own computer.

**Download:** [latest release](https://github.com/4bdulllahh/GeoHarvest/releases/latest) ·
**Version:** 0.3.0 (free beta) · **Works on:** Windows 10 and 11 · **Countries:** all of them

[![Build](https://github.com/4bdulllahh/GeoHarvest/actions/workflows/build.yml/badge.svg)](https://github.com/4bdulllahh/GeoHarvest/actions/workflows/build.yml)
[![Latest release](https://img.shields.io/github/v/release/4bdulllahh/GeoHarvest?label=download&color=3b86dd)](https://github.com/4bdulllahh/GeoHarvest/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-3b86dd.svg)](LICENSE)
![Windows 10 and 11](https://img.shields.io/badge/Windows-10%20%7C%2011-34373f.svg)

<p align="center"><img src="docs/screenshots/leads.png" alt="The Leads page: 60 dental clinics with AI score, Good fit verdicts, a one-line reason, the owner's name, phone and email" width="860" /></p>

> **Free while in beta.** Please [report anything confusing or broken](https://github.com/4bdulllahh/GeoHarvest/issues/new).
> The businesses and people in these screenshots are made up.

## Features

- **Any business, anywhere.** Pick business types from a grouped list (Marketing, Health,
  Food, Property, Shops...) that narrows as you type, or type your own. Then choose where:
  - **Countries and cities.** Switch on the countries you want, including the whole
    **European Union** or the **Gulf (GCC)** in one click, then the cities in them. Any town
    that isn't listed can be added.
  - **Around a place.** Type an address or area ("Dubai Marina", "5th Avenue, New York") and a
    distance from 1 to 100 km. GeoHarvest finds it on the map, covers the circle in small map
    views and keeps only the businesses inside it.
- **Fast.** GeoHarvest asks Google Maps for results directly instead of driving a web browser
  and clicking every listing, and it searches several cities or map views at once. In testing
  it found 1,377 dentists across the Netherlands, the UAE and the US in 47 seconds, and every
  dentist within 3 km of Dubai Marina in 7 seconds.
- **More results.** Google's own map stops at about 120 places; GeoHarvest pages through to
  about 200 per city and business type, and an area search adds more by splitting the map.
- **Maximum detail on every lead.** Name, category, phone (local and international), website,
  rating, number of reviews, address split into street, area, city, postal code and country,
  map coordinates, opening hours, price level, description, features (wheelchair access,
  women-owned...), whether the owner has claimed the listing, and links to the Google Maps
  page and its reviews.
- **Emails and social media.** GeoHarvest reads each business's website (the home page and its
  contact, about and team pages) for email addresses and Facebook, Instagram, LinkedIn, X,
  YouTube and TikTok links. It decodes hidden ("protected") emails, puts the business's own
  addresses first and throws away template ones such as `you@example.com`.
- **The owner's name (optional).** It looks for the owner or founder on the website ("Founder:
  Jane Smith", "Jane Smith, Owner", the page's business data) and in the domain's registration
  record, plus the owner's **LinkedIn profile** when the website links it. The company's
  LinkedIn page comes from its website too; "N/A" means the website doesn't link one.
- **Company age.** Google Maps doesn't record when a company was founded, so GeoHarvest
  estimates it from when the business's website was registered or first appeared online. Pick
  **startups** (under 3 years), **established** companies, or your own range in years.
- **Requirements that find the right businesses.** Click a requirement to switch it on or off.
  - **Sliders** for the Google rating, the number of reviews (few reviews often means a
    business that needs more customers) and the company age.
  - Must have an **email**, a **phone number**, **social media**, **LinkedIn**, the **owner's
    name**, an address shown on Google, opening hours listed, or a listing claimed by the owner.
  - Website: **any, has one, or none**. "No website" finds businesses you could build a site for.
  - **Opening hours**: open now, open 24 hours, open on weekends, or open on a day and time you
    pick, each in the business's own time zone.
  - Leave out closed businesses and businesses you found in earlier searches.
- **Minimum leads.** Say how many leads you need: GeoHarvest keeps searching, digging deeper
  into each city, until at least that many businesses meet your requirements, and keeps every
  match it finds, best first.
- **For cold email, cold calling or your own database.** **Quick setup** sets the requirements
  for each in one click, and **presets** save your own for next time.
- **Only the details you need.** Click any detail to leave it out before a search (Details to
  include) or after it (Columns): selected ones are highlighted, the rest greyed out. Exports
  contain only the selected columns.
- **Smart mode (optional).** Connect an AI and describe your ideal customer in plain words. The
  AI checks every business is genuine and gives it a score from 0 to 100, a verdict (Good fit,
  Maybe, Poor fit) and a one-line reason, and can leave out poor fits for you. Works with free
  AIs (Google Gemini, Groq, OpenRouter, Mistral), paid ones (Claude, OpenAI, DeepSeek) and
  **AI running on your own computer** (Ollama, LM Studio). You bring your own key; GeoHarvest
  has none built in.
- **Live results.** Leads appear while the search runs, with tiles counting leads, searches,
  websites checked, emails, phones and AI scores. The form estimates how long a search will
  take, and Windows tells you when it is done if you are working in another window.
- **Every lead scored.** A quality score from what is known about the business (email, phone,
  website, owner, social media, reviews...), with the breakdown in the lead's window.
- **Find the leads you want.** **Sort** by best lead, quality or AI score, name, city, rating,
  reviews or date found. **Show** only leads with an email, a phone, a website, the owner's
  name, social media, LinkedIn, good fits, or those **not exported yet**. Filter by the date
  found, rating and reviews, or by typing. **Copy the emails or phone numbers** in one click.
- **Everything about a business in one window.** Double-click a lead to see every detail, with
  clickable links, **Copy all** and **Open in Google Maps**.
- **Export anywhere.**
  - **Excel** with clickable links, or a plain **CSV**.
  - CSV files ready to import into **HubSpot, Pipedrive, Zoho CRM and Salesforce**, using each
    CRM's own column names, and into **HomingPigeon** (one row per email) for cold email.
  - **Copy for Google Sheets**: copies the leads and opens a new sheet; press Ctrl+V.
  - Safe against spreadsheet formula tricks hidden in business names.
- **Nothing is ever lost.** Every result is saved the moment it arrives. Stop a search, close
  the app, or have Google ask GeoHarvest to slow down, and **Resume** carries on exactly where
  it stopped.
- **Past searches.** Load any search's leads, resume it, run it again or delete it. Delete
  single leads you don't want.
- **Backups.** Back up your searches, leads, presets and settings to a file, and restore them
  on this PC or a new one. GeoHarvest also backs up by itself once a week.
- **Proxies (optional).** For people who search a lot: paste HTTP or SOCKS5 proxies in Settings
  and test them. GeoHarvest takes turns between them and skips any that stop working.
- **Updates itself.** Every time it opens, GeoHarvest downloads the newest version, checks it is
  genuine and installs it, waiting for a running search to finish. Your searches and settings
  are kept. An older download installs the newest version too.
- **Light and easy to install.** A 33 MB download with its own installer: no administrator
  rights, no Python, nothing else to install, and Cancel never leaves a half-installed app.
- **Your look, your language.** Ready-made themes plus a theme maker (share your theme as a
  file), four text sizes, high contrast, bold text, smooth scrolling, and the menu in the order
  you want. In **English, Arabic, German, Spanish and French**. The window fits any size: below
  about 1000 pixels the menu shrinks to icons.
- **Start here.** A guide page walks you through your first search, export and backup.

## Screenshots

<p align="center"><img src="docs/screenshots/search.png" alt="New search: dentist and dental clinic, Around a place, Dubai Marina within 5 km, with the plan of 8 searches" width="860" /></p>

| Requirements: sliders, must haves and opening hours | A search running, with live tiles |
| --- | --- |
| <img src="docs/screenshots/filters.png" alt="Requirements: Quick setup, company age, rating and reviews sliders with reviews up to 150, Minimum leads, website any, has or none, must-have buttons, and Open on weekends selected" width="420" /> | <img src="docs/screenshots/search-running.png" alt="A search in step 2 of 3: 1,412 businesses found, 16 of 16 searches done, 298 of 450 websites checked, 187 with an email, 1,290 with a phone, best leads still to be picked out of 300" width="420" /> |

| Everything about one business | Columns: select the details to show |
| --- | --- |
| <img src="docs/screenshots/lead.png" alt="The details window for a dental clinic: AI score and reason, owner and where it was found, the owner's LinkedIn profile, phone, email, website, rating, company age, opening hours and address" width="380" /> | <img src="docs/screenshots/columns.png" alt="The Columns window: select buttons grouped into Business, Owner, Contact, Social media, Reviews, Location, Company age, Smart mode and Other" width="440" /> |

<p align="center"><img src="docs/screenshots/exports.png" alt="The More exports menu: CSV file, CSV for HubSpot, Pipedrive, Zoho CRM and Salesforce, and Copy for Google Sheets" width="860" /></p>

| Smart mode: your AI, your ideal customer | Settings: everyday use, speed and proxies |
| --- | --- |
| <img src="docs/screenshots/smart.png" alt="Smart mode: AI providers from Google Gemini to LM Studio on this PC, the key box, the model and the ideal customer description" width="420" /> | <img src="docs/screenshots/settings.png" alt="Settings: first page, date and time formats, the finished-search notification, search speed, and the proxies box with three example proxies, 3 of 3 working" width="420" /> |

<p align="center"><img src="docs/screenshots/history.png" alt="Past searches: an area search and a five-city search, with Load, Resume and Run again, and the Search loaded toast" width="860" /></p>

## How it works

1. **New search.** Click the business box and pick types from the list, or type your own.
   Choose **Countries and cities** or **Around a place**. Use a **Quick setup** or pick your
   **Requirements**, set **Minimum leads** and the details to include. Press **Start search**.
2. **Watch it work.** The search runs in three steps: searching Google, checking websites,
   picking the best leads. The tiles count businesses found, searches, websites checked,
   emails, phones, AI scores (in Smart mode) and the leads found. Press **Stop** whenever you
   like; you keep everything found so far, and **Resume** in Past searches carries on later.
   If there weren't enough businesses, it tells you why and offers to add more cities.
3. **Leads.** The page opens on your latest search. Use **Show** and **Sort**, double-click a
   lead for its details, delete the ones you don't want, and use **Columns** to choose what
   shows.
4. **Export.** **Export to Excel**, or **More exports** for CSV, your CRM or Google Sheets. The
   export has exactly the rows and columns on screen, in that order.

### Smart mode

1. Open **Smart mode** and choose an AI. **Google Gemini** is a good free start: press **Get a
   free key**, sign in with a Google account, copy the key and paste it in. For a free,
   private AI on your own PC, install [Ollama](https://ollama.com/download), run
   `ollama pull llama3.2`, and choose **Ollama (on this PC)**.
2. Press **Load models** and pick one.
3. Describe your ideal customer: what you sell, who buys it and who is not worth contacting.
4. Press **Save and test**. GeoHarvest asks the AI to score a sample business, so you know it
   works before a real search.
5. Switch on **Smart mode** on the New search page. To score a search you already ran, open it
   on the Leads page and press **Score with AI**.

## Install

1. Download `GeoHarvest-vX.Y.Z-windows.zip` from the
   [latest release](https://github.com/4bdulllahh/GeoHarvest/releases/latest).
2. Right-click it and choose **Extract All** (Setup can't run from inside the zip).
3. Open the extracted folder, double-click **GeoHarvest-Setup.exe** and click **Install**. At
   the end, choose the Start menu entry, a desktop shortcut and whether GeoHarvest opens when
   Windows starts. No administrator rights needed.

**"Windows protected your PC"?** GeoHarvest is new and not yet code-signed (a signing
certificate costs money every year), so Windows SmartScreen doesn't recognise it. Press
**More info**, then **Run anyway**. You only need to do this once.

**"Smart App Control blocked an app"?** Some Windows 11 PCs block every program that isn't
code-signed, with no Run anyway. GeoHarvest can't be installed on those PCs yet; a backup
installer for them is coming in 0.3.1.

Your searches, leads and settings are kept in `%APPDATA%\GeoHarvest`, outside the app folder,
so updating never loses them. To remove GeoHarvest, use **Settings > Uninstall GeoHarvest** or
Windows Settings > Apps; it asks whether to keep your data.

## Privacy

GeoHarvest has no accounts, no servers of its own, no analytics and no tracking. Everything
stays in `%APPDATA%\GeoHarvest` on your computer, and your AI key and proxies are encrypted so
only your Windows account can read them. It connects only to Google Maps, the websites of the
businesses it finds, domain-record and web-archive lookups, the AI you choose (which never
receives emails, phone numbers or owners' names) and GitHub for updates. The full list is in
[PRIVACY.md](PRIVACY.md).

## Principles

- **Free for good.** No paid APIs, no proxies you have to buy, no subscription. You bring the AI
  if you want one.
- **Nothing slow on screen.** Searching, website visits, AI and exports all run in the
  background, so the window never freezes.
- **Never lose a result.** Every page of results is saved as it arrives, and every search can
  be resumed.
- **Plain words.** No jargon on screen, in any of its five languages; every setting says what it does.
- **The logic is tested without the UI.** `app/core` never touches the interface, and its
  tests run without a network.

## Tech stack

| Area | Choice |
| --- | --- |
| Language | Python 3.12 |
| Interface | PyQt6 (Qt 6 Widgets), Fusion style, one stylesheet coloured by the chosen theme; five languages, Arabic right to left |
| Google Maps | Plain HTTPS with httpx (no browser, no API key), HTTP and SOCKS5 proxies |
| Websites | httpx, 16 at a time; RDAP for domain age and registrant, the Wayback Machine as a fallback |
| Smart mode | Google Gemini and OpenAI-compatible services over HTTPS, Claude through the official `anthropic` SDK |
| Storage | SQLite, one JSON document per lead; keys and proxies encrypted with Windows DPAPI |
| Export | openpyxl for Excel, Python's csv for CSV and CRM files |
| Installer | Its own, written in Python with Tkinter, built with PyInstaller (one folder, not one file) |
| Quality | pytest (no network needed), a packaged self-test, GitHub Actions on every push |

## How a search works

The Google Maps page fetches its result list as JSON from `google.com/search?tbm=map&pb=...`,
20 places at a time. GeoHarvest sends the same request, with the long `pb` parameter
captured from a real browser session, and pages through until Google runs out (about 200
places).

- **Countries and cities** become one query per city and business type ("dentist in Dubai,
  United Arab Emirates"), run several at a time.
- **Around a place**: GeoHarvest first asks Google where the place is. It then covers the
  circle with map views at most 5 km across (up to 8 x 8), searches each one with the map put
  there, stops paging a view as soon as a page has nothing inside it, and keeps only the
  businesses inside the circle.
- **Three steps, one after the other.** 1: search Google and keep every business that passes
  the filters that need only Google's data (rating, reviews, website, phone, address, opening
  hours, closed businesses). 2: visit the websites of the most promising ones for emails,
  social media, company age and the owner. 3: score each lead (phone, website, email, rating,
  reviews, owner, social media, claimed listing...; averaged with the AI score in Smart mode)
  and rank the best first. If fewer than **Minimum leads** meet your requirements, GeoHarvest
  goes back to step 1 and digs deeper into each city, until it has enough or Google runs out.
- **If there aren't enough**, GeoHarvest says why ("71 company age unknown, 44 older than 3
  years...") and offers to add more cities or allow any company age, carrying on from where it
  stopped.
- **Hidden addresses.** Some businesses hide their address on Google. GeoHarvest marks them
  "Service area", takes the city from the search when Google's rough pin is near it, and
  leaves out pins far away. "Must show its address" leaves them all out.
- **Opening hours** are read from Google's text ("Monday: 9 AM-5 PM; Friday: 6 PM-2 AM...")
  and checked in the business's own time zone, including late nights that run past midnight.

## Good to know

- **Results per search.** Google shows about 200 businesses per city and business type. For
  more leads, choose more cities, use Around a place, or add business types (`dentist, dental
  clinic, orthodontist`). Strict filters (Startups, must have a phone and a website) can leave
  small cities with only a few; the summary after the search says what was left out and why.
- **"Google asked GeoHarvest to slow down."** Very large searches from one internet connection
  can hit Google's limits. GeoHarvest pauses, keeps everything found, and you can resume from
  Past searches after about 15 minutes. **Gentle** speed in Settings, or proxies, make this
  less likely.
- **Company age is an estimate** based on the website's domain. Some registries (`.pk`, `.de`,
  `.ae`) don't publish dates; for those GeoHarvest uses the first time the site appeared in the
  Internet Archive, which is slower, so it only does that when you filter by age. If neither
  has a date, the age shows as **Unknown**; those leads are kept and ranked after the rest.
- **Owners' names and LinkedIn** are found only when the website or the domain record states
  them, so expect them for some businesses, not all. **N/A** in a LinkedIn column means the
  business's website doesn't link one.
- **"Service area"** in the address means the business hides its address on Google (common
  for agencies and trades that visit customers). Turn on **Must show its address** to leave
  them out.
- **Emails** come from the business's own website. Businesses with only a Facebook or
  Instagram page get that link but no email, because those sites block automated visits.

## Testing the beta

The most useful feedback: what you searched for and what went wrong or looked odd, anything
confusing, and what you wish it did. New in 0.3.0 and worth trying: a **Quick setup** with
**Minimum leads** set high, the **Show** and **Sort** menus on the Leads page, the themes, and
the app in another language. Post it as a
[GitHub issue](https://github.com/4bdulllahh/GeoHarvest/issues/new). If the app crashed,
attach `%APPDATA%\GeoHarvest\logs\crash.log`; if Setup failed, attach
`%TEMP%\GeoHarvest-setup-log.txt` (Setup's **Open log file** button shows it).

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
(`.github/workflows/build.yml`). [HANDOVER.md](HANDOVER.md) explains how everything works, the
decisions behind it, and where each feature lives.

## Roadmap

- [x] **1. Shell**: the window, theme, sidebar and logo
- [x] **2. Search engine**: Google Maps search without a browser, city by city, saved as it goes
- [x] **3. Search and Leads**: the search form, live table, filters, Excel and CSV export
- [x] **4. Enrichment**: emails and social links from websites, company age
- [x] **5. Smart mode**: AI lead scoring with free, paid and on-your-PC AIs
- [x] **6. History and updates**: past searches, resume, auto-update, settings, every country
- [x] **7. Release**: the Windows download, automatic builds, this README (v0.1.0)
- [x] **v0.1.1 and v0.1.2**: our own installer, uninstall, exact lead counts, a Stop that stops
- [x] **v0.2**: a fixed and faster installer, a smaller download, lead details, deleting leads,
  choosing columns, Load from Past searches
- [x] **v0.2.1**: search around a place, rating and reviews at most, website any/has/none,
  opening hours, owners' names, Columns, CRM exports, Copy for Google Sheets, proxies, switches
- [x] **v0.2.2**: searches in three steps, the best leads shared fairly between cities and
  business types, reasons when a search comes up short, a business-type list, LinkedIn
  from websites, hidden addresses fixed
- [x] **v0.3.0**: Requirements with sliders, Minimum leads, Quick setup and presets, quality
  score, Show and Sort, themes, five languages, backups, updates that install by themselves
- [ ] **v0.3.1**: a backup installer for PCs with Smart App Control
- [ ] **Ideas for later**: emails from Facebook pages, a map view of results, and a Mac version

## Legal

- [LICENSE](LICENSE): GeoHarvest's code is MIT licensed.
- [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md): the libraries and data GeoHarvest uses and
  their licenses. The Windows download includes PyQt6, so the download as a whole is
  distributed under the GPL v3.
- [PRIVACY.md](PRIVACY.md): what is stored, and what is sent where.
- [DISCLAIMER.md](DISCLAIMER.md): acceptable use, data protection and marketing laws, and no
  warranty. GeoHarvest is not affiliated with Google.
- [SECURITY.md](SECURITY.md): how to report a security problem.

## License

[MIT](LICENSE) © 2026 Abdullah
