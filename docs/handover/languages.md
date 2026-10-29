# Languages

English, Arabic (right to left), German, Spanish and French. Read this before adding or changing any text on screen.

| Topic | Decision |
|---|---|
| Languages (0.3) | `app/i18n/` is HomingPigeon's package: `t(english, **fields)` translates at display time (English is the key; anything missing or with broken fields falls back to English), catalogs in `app/i18n/locales/<code>.json` (bundled by `tools/build.py --add-data`). Settings > Language switches at once (`MainWindow.change_language` saves `language`, sets the layout direction, rebuilds); with nothing chosen the computer's language is used (`prefs.language`). Arabic is right to left. Write UI text as `t("... {count:,} ...", count=n)`, never an f-string, and give plurals their own sentence. After changing text run `python tools/i18n.py missing <code>`, add the translations, then `check`; `tests/test_i18n.py` fails on a missing string, different `{fields}` or lost edge spaces. Not translated on purpose: business data from Google, business types (Google searches with them), exported column headings (CRMs read them), AI provider notes, the AI's own reasons. Terms: de formal Sie + "Leads"; es tú + "leads"; fr vous + "prospects"; ar العملاء المحتملون |
