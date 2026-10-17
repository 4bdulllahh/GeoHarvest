# Third-party notices

GeoHarvest's own code is released under the [MIT License](LICENSE). The Windows download
also contains other people's software and data, each under its own license, listed below.
The full license texts travel with the download, in the `licenses` folder of the zip and of
the installed app (`%LOCALAPPDATA%\Programs\GeoHarvest\licenses`).

## The Windows download as a whole is GPL v3

GeoHarvest's window, buttons and tables are drawn with **PyQt6**, which is licensed under
the **GNU General Public License v3**. Because the Windows download combines GeoHarvest with
PyQt6, that download is distributed under the terms of the GPL v3. In practice:

- You may use, copy, share and change it freely.
- If you pass a copy of the download on, you must pass these license terms on with it and
  offer the source code. The complete source of every version is in this repository: each
  release's source is under its tag on the
  [Releases page](https://github.com/4bdulllahh/GeoHarvest/releases).
- GeoHarvest's own source code stays under the MIT License, which is compatible with the
  GPL. You can reuse it in your own projects under MIT.

## Software

| Component | What GeoHarvest uses it for | License |
|---|---|---|
| [Python](https://www.python.org/) | The language GeoHarvest and its installer run on | PSF License |
| [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) | The app's window and controls | GPL v3 |
| [Qt 6](https://www.qt.io/) (QtCore, QtGui, QtWidgets, QtSvg) | The toolkit under PyQt6 | LGPL v3 |
| [PyQt6-sip](https://pypi.org/project/PyQt6-sip/) | Connects Python to Qt | BSD 2-Clause |
| [httpx](https://www.python-httpx.org/), httpcore, h11 | Google Maps searches, website visits, AI requests | BSD 3-Clause, BSD 3-Clause, MIT |
| [socksio](https://github.com/sethmlarson/socksio) | SOCKS5 proxies | MIT |
| [anyio](https://github.com/agronholm/anyio), [sniffio](https://github.com/python-trio/sniffio) | Used by httpx | MIT, MIT or Apache 2.0 |
| [idna](https://github.com/kjd/idna) | International web addresses | BSD 3-Clause |
| [certifi](https://github.com/certifi/python-certifi) | Trusted certificates for secure connections | MPL 2.0 |
| [openpyxl](https://openpyxl.readthedocs.io/), et-xmlfile | Excel export | MIT |
| [anthropic](https://github.com/anthropics/anthropic-sdk-python) and what it uses (httpx2, httpcore2, pydantic, pydantic-core, jiter, docstring-parser, typing-extensions, typing-inspection, annotated-types, opentelemetry-api) | Smart mode with Claude, only with your own key | MIT (typing-extensions: PSF; httpx2, httpcore2: BSD 3-Clause; opentelemetry-api: Apache 2.0) |
| [tzdata](https://github.com/python/tzdata) | Time zones for the "Open now" filter | Apache 2.0 |
| OpenSSL, SQLite, libffi, zlib, Tcl/Tk (inside Python) | Secure connections, the saved data, the installer's window | Apache 2.0, public domain, MIT, zlib, Tcl/Tk license |

The exact versions are the ones in `licenses/` of each download. Qt is shipped as separate
DLL files in the app's `_internal` folder, so it can be replaced with another build of the
same Qt version, as the LGPL allows.

## Data

**Countries and cities** (`app/data/cities.json`) come from [GeoNames](https://www.geonames.org/),
licensed under [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).
GeoHarvest uses a reduced copy: each country's biggest cities by population.

## Names and trademarks

Google and Google Maps are trademarks of Google LLC. Claude and Anthropic are trademarks of
Anthropic PBC. Other company, product and service names (HubSpot, Pipedrive, Zoho,
Salesforce, Gemini, OpenAI, Groq, OpenRouter, Mistral, DeepSeek, Ollama, LM Studio, LinkedIn,
Facebook, Instagram, X, YouTube, TikTok) belong to their owners. GeoHarvest is not affiliated
with, endorsed by or sponsored by any of them. The names are used only to say what GeoHarvest
works with.
