"""Settings: appearance, search speed, updates and the user's data."""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import config
from app.core import credentials, db, prefs, scraper
from app.i18n import t
from app.services import updater
from app.ui.pages.base import Page
from app.ui.widgets.common import (ChoiceButtons, FormRow, Section, danger_button, hint, muted,
                                   open_url, row, secondary_button)
from app.ui.widgets.dialogs import ChoiceDialog, ConfirmDialog
from app.ui.widgets.inputs import checkbox, text_box
from app.workers.base import Task

SPEEDS = [("2", "Gentle"), ("4", "Normal"), ("8", "Fast")]


class SettingsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.add_header("Settings", "How GeoHarvest looks and behaves.")
        body = self.scroll_body()
        layout = body.body_layout

        look = Section("Appearance")
        theme_row = FormRow("Theme")
        theme_row.add(ChoiceButtons(prefs.THEMES, prefs.get("appearance"),
                                    on_change=window.change_appearance))
        look.add(theme_row)
        size_row = FormRow("Text size")
        size_row.add(ChoiceButtons([(k, label) for k, label, _ in prefs.TEXT_SIZES],
                                   prefs.get("text_size"), on_change=window.change_text_size))
        look.add(size_row)
        look.add(checkbox("High contrast", bool(prefs.get("high_contrast")),
                          on_change=window.change_contrast))
        look.add(checkbox("Bold text", bool(prefs.get("bold_text")),
                          on_change=window.change_bold_text))
        layout.addWidget(look)

        speed = Section("Search speed",
                        "How many cities GeoHarvest searches at the same time.")
        speed.add(ChoiceButtons(SPEEDS, str(db.get_setting("parallel_searches", 4)),
                                on_change=lambda v: db.set_setting("parallel_searches", int(v))))
        speed.add(hint("Fast finishes big searches sooner, but Google is more likely to ask "
                       "GeoHarvest to slow down. If that happens, the search pauses and you can "
                       "resume it later from Past searches. Applies to the next search."))
        layout.addWidget(speed)

        proxies = Section("Proxies (optional)",
                          "For people who search a lot. GeoHarvest sends its Google Maps "
                          "searches through these, taking turns, and skips any that stop working "
                          "or that Google slows down. Website visits and AI go direct.")
        self.proxies = text_box("One per line, for example:\n1.2.3.4:8080\n"
                                "user:password@1.2.3.4:8080\n1.2.3.4:8080:user:password\n"
                                "socks5://1.2.3.4:1080", monospace=True, lines=6)
        self.proxies.setPlainText(credentials.load_secret(scraper.PROXIES_SECRET))
        proxies.add(self.proxies)
        self.proxy_status = hint("")
        self.test_button = secondary_button("Test them", self.test_proxies)
        proxies.add(row(secondary_button("Save", self.save_proxies), self.test_button,
                        self.proxy_status, stretch=2))
        proxies.add(hint("Kept encrypted on this computer, since proxies often include a "
                         "password. Leave the box empty to search without proxies. Applies to "
                         "the next search."))
        layout.addWidget(proxies)

        updates = Section("Updates", t("You have GeoHarvest {version}. Each time it opens, "
                                       "GeoHarvest checks for a newer version and installs it "
                                       "by itself, waiting while a search runs.",
                                       version=config.APP_VERSION))
        updates.add(row(secondary_button("Check now",
                                         lambda: window.check_for_update(tell_if_none=True)),
                        secondary_button("Open the GitHub page",
                                         lambda: open_url(config.REPO_URL)), None))
        layout.addWidget(updates)

        data = Section("Your data",
                       "Searches, leads, settings and your encrypted AI key are kept on this "
                       "computer only, in your user folder. Updating GeoHarvest never touches them.")
        data.add(row(secondary_button("Open the data folder",
                                      lambda: os.startfile(config.DATA_DIR)),  # noqa: S606
                     danger_button("Delete all searches and leads...", self.delete_all), None))
        layout.addWidget(data)

        if updater.uninstaller():
            remove = Section("Uninstall", "Remove GeoHarvest from this computer.")
            remove.add(row(danger_button("Uninstall GeoHarvest...", self.uninstall), None))
            layout.addWidget(remove)

        fair = Section("Use it fairly")
        fair.add(muted("GeoHarvest reads public Google Maps listings and business websites. "
                       "When you contact the businesses you find, follow the rules where you "
                       "and they are, such as GDPR in the EU and UK, CAN-SPAM in the US and the "
                       "UAE's data protection law, and Google's terms of service."))
        layout.addWidget(fair)

        about = Section("About")
        about.add(muted(f"GeoHarvest {config.APP_VERSION}, © 2026 Abdullah. Free software: "
                        "GeoHarvest's code is MIT licensed, and this download, which includes "
                        "PyQt6, is distributed under the GNU GPL v3. It comes with no warranty. "
                        "Not affiliated with Google."))
        about.add(row(secondary_button("Open the licenses", self.open_licenses),
                      secondary_button("Source code", lambda: open_url(config.REPO_URL)), None))
        layout.addWidget(about)
        layout.addStretch(1)

    def open_licenses(self) -> None:
        """The licenses folder beside the installed app, or the notices page from source."""
        folder = Path(sys.executable).parent / "licenses"
        if getattr(sys, "frozen", False) and folder.is_dir():
            os.startfile(folder)  # noqa: S606
        else:
            open_url(f"{config.REPO_URL}/blob/main/THIRD-PARTY-NOTICES.md")

    def save_proxies(self) -> None:
        good, bad = scraper.parse_proxies(self.proxies.toPlainText())
        if bad:
            self.notify("These lines aren't proxies: " + ", ".join(bad[:3]) +
                        (" and more" if len(bad) > 3 else "") + ". Fix them, then save again.",
                        "warn", 8000)
            return
        credentials.save_secret(scraper.PROXIES_SECRET, "\n".join(good))
        self.proxies.setPlainText("\n".join(good))
        self.notify(f"Saved {len(good)} {'proxy' if len(good) == 1 else 'proxies'}." if good
                    else "Proxies cleared: searches go direct.", "success")

    def test_proxies(self) -> None:
        good, bad = scraper.parse_proxies(self.proxies.toPlainText())
        if bad or not good:
            self.proxy_status.setText("Nothing to test." if not bad else
                                      "Fix the lines that aren't proxies first.")
            return

        def check_all() -> list[str | None]:
            with ThreadPoolExecutor(8) as pool:
                return list(pool.map(scraper.check_proxy, good))

        def done(results: list[str | None]) -> None:
            working = sum(r is None for r in results)
            failed = [f"{proxy.split('@')[-1]}: {r}" for proxy, r in zip(good, results) if r]
            self.proxy_status.setText(f"{working} of {len(good)} working." + (
                " Not working: " + "; ".join(failed[:3]) + (" ..." if len(failed) > 3 else "")
                if failed else ""))

        self.test_button.setEnabled(False)
        self.proxy_status.setText(f"Testing {len(good)}...")
        Task(check_all).start(
            on_result=self.guard(done),
            on_error=self.guard(lambda message: self.proxy_status.setText(message)),
            on_done=self.guard(lambda: self.test_button.setEnabled(True)))

    def delete_all(self) -> None:
        if self.window_.busy_page_reason():
            self.notify("Wait until the search has finished, or stop it first.", "warn")
            return
        if not ConfirmDialog.ask(self, "Delete every search and lead?",
                                 "This empties GeoHarvest's lead lists. Files you exported are "
                                 "not touched, and your settings and AI key are kept.",
                                 confirm_text="Delete everything", danger=True):
            return
        db.execute("DELETE FROM leads")
        db.execute("DELETE FROM searches")
        self.window_.refresh_status()
        self.notify("All searches and leads deleted.", "success")

    def uninstall(self) -> None:
        if self.window_.busy_page_reason():
            self.notify("Wait until the search has finished, or stop it first.", "warn")
            return
        choice = ChoiceDialog.ask(
            self, "Uninstall GeoHarvest?",
            "GeoHarvest will close and be removed from this computer, with its shortcuts.",
            [("keep", "Uninstall, keep my searches, leads and settings", "danger"),
             ("delete", "Uninstall and delete my searches, leads and settings too", "secondary"),
             (None, "Cancel", "secondary")])
        if choice is None:
            return
        try:
            updater.start_uninstall(delete_data=choice == "delete")
        except OSError as error:
            self.notify(f"The uninstaller didn't start: {error}", "error")
            return
        self.window_.quit_app()
