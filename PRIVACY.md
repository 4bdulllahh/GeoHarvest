# Privacy

GeoHarvest runs entirely on your computer. It has no accounts, no servers of its own, no
analytics and no tracking. The author of GeoHarvest never receives your searches, your
leads, your settings or your keys.

## What GeoHarvest stores, and where

Everything is kept in your Windows user folder, `%APPDATA%\GeoHarvest`:

| File | What is in it |
|---|---|
| `geoharvest.db` | Your searches, the leads they found and your settings |
| `secrets.dat` | Your AI key and your proxies, encrypted with Windows (DPAPI) so only your Windows account can read them |
| `logs\crash.log` | Technical details of the last crash, if there was one |
| A few small `.svg` files | Icons drawn for the current theme |

Setup writes a log of its last run to `%TEMP%\GeoHarvest-setup-log.txt`. Exported Excel
and CSV files go wherever you save them.

Nothing leaves your computer unless you send it (see below). To delete your data: Settings >
**Delete all searches and leads**, or uninstall and choose to delete your data, or delete the
`%APPDATA%\GeoHarvest` folder.

## What GeoHarvest connects to

| Where | When | What is sent |
|---|---|---|
| Google (`www.google.com`) | Every search | What you search for and where, like typing it into Google Maps. Through your proxies if you added any |
| Each business's own website | When "Visit each website" is on | An ordinary visit to its home page and up to three contact or about pages |
| `rdap.org` (domain registration records) | When websites are visited, or Company age is used | The website's domain name |
| `web.archive.org` (Internet Archive) | Only when you filter by Startups or Established | The website's domain name |
| The AI you chose in Smart mode | Only when Smart mode is on, or you press Score with AI | Your ideal-customer description and, for each business: name, category, rating, review count, price level, status, city, website, estimated age, whether it is claimed, description, features, opening hours and whether it has an email or social media. **Never its email addresses, phone numbers or owner's name.** Your key goes only to that AI |
| `api.github.com` and GitHub downloads | When GeoHarvest checks for updates (you can turn this off in Settings) or you press Update now | A normal request for the latest release |
| Your proxies | Only if you added them in Settings | Your Google Maps searches go through them |

Each of these services has its own privacy policy. Your AI provider's policy decides what it
does with what it receives; a model on your own computer (Ollama, LM Studio) receives the
same details but nothing leaves your computer.

"Copy for Google Sheets" only puts the leads on your clipboard and opens a blank Google
Sheet in your browser. Nothing is uploaded until you paste it yourself.

## The leads you collect

The leads are information about businesses, and sometimes about people: a sole trader's
email address, or an owner's name found on a website. Once you collect them, **you decide
what happens to them, and data protection laws apply to you** (for example the GDPR in the EU
and UK). Keep only what you need, use it fairly, and delete it when you no longer need it.
See [DISCLAIMER.md](DISCLAIMER.md).

## Questions

Open an issue on [GitHub](https://github.com/4bdulllahh/GeoHarvest/issues).
