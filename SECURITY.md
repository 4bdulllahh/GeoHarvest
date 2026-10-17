# Security

## Reporting a problem

If you find a security problem in GeoHarvest, please report it privately rather than in a
public issue: on GitHub, open the repository's **Security** tab and choose **Report a
vulnerability**. Say what you found, how to reproduce it, and which version you used
(Settings shows it).

You should get a reply within a week. Fixes go out as a normal update, which every
installed copy offers on its next start.

## Supported versions

Only the latest release gets fixes. Update from Settings > **Check now**, or download it from
the [Releases page](https://github.com/4bdulllahh/GeoHarvest/releases/latest).

## How GeoHarvest protects you

- **Your keys stay yours.** AI keys and proxies are encrypted with Windows (DPAPI), so only
  your Windows account can read them, and an AI key is only ever sent to the AI provider you
  chose. GeoHarvest has no built-in keys.
- **Checked updates.** Update now downloads the new version from GitHub over HTTPS and checks
  its SHA-256 fingerprint against the one GitHub publishes before installing it.
- **No administrator rights.** GeoHarvest installs into your own user folder and never asks
  for them.
- **Safe exports.** Text from Google and websites is written to Excel and CSV as plain text,
  so a business name such as `=HYPERLINK(...)` can't run as a formula.
- **Nothing to break into.** GeoHarvest has no server and opens no ports on your computer.

The app is not code-signed yet, which is why Windows shows "Windows protected your PC" the
first time. Download it only from this repository's Releases page.
